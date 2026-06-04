import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Dict, List

from telethon import TelegramClient
from telethon.tl.types import MessageMediaPoll

logger = logging.getLogger(__name__)

MOSCOW_TZ = timezone(timedelta(hours=3), name="MSK")
CONNECT_TIMEOUT_SECONDS = 60


class UserClient:
    def __init__(self, config_manager):
        self.config = config_manager
        self.client = None
        self.connected = False

    async def connect(self):
        if self.connected and self.client and self.client.is_connected():
            return
        session_name = self.config.get_setting("session_name", "aggregator_session")
        api_id = self.config.get_setting("api_id")
        api_hash = self.config.get_setting("api_hash")
        if not api_id or not api_hash:
            raise ValueError("Заполните API_ID и API_HASH в .env")

        self.client = TelegramClient(
            session_name,
            api_id,
            api_hash,
            connection_retries=2,
            retry_delay=5,
            request_retries=1,
            timeout=15,
        )
        try:
            await asyncio.wait_for(self.client.connect(), timeout=CONNECT_TIMEOUT_SECONDS)
            is_authorized = await asyncio.wait_for(
                self.client.is_user_authorized(),
                timeout=CONNECT_TIMEOUT_SECONDS,
            )
        except asyncio.TimeoutError as exc:
            raise TimeoutError(
                "Не удалось подключиться к Telegram user API за 60 секунд. "
                "Похоже, прямое MTProto-соединение блокируется или нестабильно."
            ) from exc

        if not is_authorized:
            logger.info("Требуется авторизация. Введите код в консоль.")
            await self.client.start()
        self.connected = True
        logger.info("User Client подключен")

    async def disconnect(self):
        if self.client:
            await self.client.disconnect()
            self.client = None
            self.connected = False
            logger.info("User Client отключен")

    async def ensure_connected(self):
        if not self.connected or not self.client or not self.client.is_connected():
            await self.connect()

    @staticmethod
    def _post_link(channel_username: str, message_id: int) -> str:
        channel_clean = channel_username.lstrip("@")
        return f"https://t.me/{channel_clean}/{message_id}"

    def _analysis_window(self):
        schedule_time = self.config.get_setting("schedule_time", "08:00")
        schedule_hour, schedule_minute = map(int, schedule_time.split(":"))
        now_moscow = datetime.now(MOSCOW_TZ)
        reference_moscow = now_moscow.replace(
            hour=schedule_hour,
            minute=schedule_minute,
            second=0,
            microsecond=0,
        )
        window_start_moscow = reference_moscow - timedelta(hours=48)
        window_end_moscow = reference_moscow - timedelta(hours=24)
        return (
            window_start_moscow,
            window_end_moscow,
            window_start_moscow.astimezone(timezone.utc),
            window_end_moscow.astimezone(timezone.utc),
        )

    async def get_best_post(self, channel_username: str, window_start_utc: datetime, window_end_utc: datetime):
        try:
            messages = []

            async for message in self.client.iter_messages(channel_username, offset_date=window_end_utc, limit=200):
                if message.date < window_start_utc:
                    break
                if message.date >= window_end_utc:
                    continue
                if isinstance(message.media, MessageMediaPoll):
                    continue
                if not message.text and not message.media:
                    continue

                reactions_count = 0
                if message.reactions:
                    for reaction in message.reactions.results:
                        reactions_count += reaction.count

                messages.append((message, reactions_count))

            if not messages:
                return None

            messages.sort(key=lambda x: (x[1], x[0].views or 0), reverse=True)
            message, reactions = messages[0]
            channel_id = message.peer_id.channel_id if hasattr(message.peer_id, "channel_id") else 0
            entity = await self.client.get_entity(channel_username)
            channel_title = entity.title if hasattr(entity, "title") else channel_username

            return {
                "channel_id": channel_id,
                "message_id": message.id,
                "channel": channel_username,
                "channel_title": channel_title,
                "reactions": reactions,
                "views": message.views or 0,
                "link": self._post_link(channel_username, message.id),
            }
        except Exception as e:
            logger.error(f"Ошибка при анализе канала {channel_username}: {e}")
            raise

    async def collect_posts(self):
        await self.ensure_connected()

        source_channels = self.config.get_source_channels()
        if not source_channels:
            raise ValueError("Активная подборка пустая: в collections.json нет каналов")

        window_start_moscow, window_end_moscow, window_start_utc, window_end_utc = self._analysis_window()

        reports = [
            "Окно анализа: "
            f"{window_start_moscow.strftime('%d.%m.%Y %H:%M')} - "
            f"{window_end_moscow.strftime('%d.%m.%Y %H:%M')} МСК"
        ]
        candidates = []

        for channel in source_channels:
            try:
                result = await self.get_best_post(channel, window_start_utc, window_end_utc)
                if result is None:
                    reports.append(f"Канал {channel}: постов позавчера не было")
                    continue
                candidates.append(result)
                reports.append(
                    f"Канал {channel}: {result['reactions']} реакций, {result['views']} просмотров\n{result['link']}"
                )
            except Exception as e:
                error_msg = str(e)
                if "CHANNEL_PRIVATE" in error_msg:
                    reports.append(f"Канал {channel}: недоступен (приватный)")
                elif "USERNAME_NOT_OCCUPIED" in error_msg:
                    reports.append(f"Канал {channel}: не существует")
                else:
                    reports.append(f"Канал {channel}: ошибка - {error_msg}")

        if not candidates:
            reports.append("\nНет постов для отправки")
            return [], reports

        reports.append(f"\nНайдено лучших постов: {len(candidates)} из {len(source_channels)} каналов")
        return candidates, reports

    def mark_as_posted(self, items: List[Dict]):
        for item in items:
            self.config.add_posted(
                channel_id=item["channel_id"],
                message_id=item["message_id"],
                channel_title=item["channel"],
            )
