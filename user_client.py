import logging
from datetime import datetime, timedelta
from typing import List, Tuple, Dict
from telethon import TelegramClient
from telethon.tl.types import MessageMediaPoll

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class UserClient:
    def __init__(self, config_manager):
        self.config = config_manager
        self.client = None
        self.connected = False
    
    async def connect(self):
        if self.connected and self.client and self.client.is_connected():
            return
        session_name = self.config.get_setting('session_name', 'aggregator_session')
        api_id = self.config.get_setting('api_id')
        api_hash = self.config.get_setting('api_hash')
        if not api_id or not api_hash:
            raise ValueError("Заполните api_id и api_hash в config.json")
        self.client = TelegramClient(session_name, api_id, api_hash)
        await self.client.connect()
        if not await self.client.is_user_authorized():
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
    
    async def get_best_post(self, channel_username: str, target_date: datetime):
        try:
            end_date = target_date + timedelta(days=1)
            messages = []
            async for message in self.client.iter_messages(channel_username, offset_date=end_date, limit=100):
                if message.date.replace(tzinfo=None) < target_date:
                    break
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
            messages.sort(key=lambda x: x[1], reverse=True)
            for message, reactions in messages:
                channel_id = message.peer_id.channel_id if hasattr(message.peer_id, 'channel_id') else 0
                if not self.config.is_posted(channel_id, message.id):
                    entity = await self.client.get_entity(channel_username)
                    channel_title = entity.title if hasattr(entity, 'title') else channel_username
                    return {
                        'channel_id': channel_id,
                        'message_id': message.id,
                        'channel': channel_username,
                        'channel_title': channel_title,
                        'reactions': reactions,
                        'views': message.views or 0
                    }
            return None
        except Exception as e:
            logger.error(f"Ошибка при анализе канала {channel_username}: {e}")
            raise
    
    async def collect_posts(self):
        await self.ensure_connected()
        source_channels = self.config.get_setting('source_channels', [])
        if not source_channels:
            raise ValueError("Не указаны каналы-источники")
        now = datetime.now()
        yesterday = now - timedelta(days=1)
        target_date = datetime(yesterday.year, yesterday.month, yesterday.day, 0, 0, 0)
        reports = []
        candidates = []
        for channel in source_channels:
            try:
                result = await self.get_best_post(channel, target_date)
                if result is None:
                    reports.append(f"❌ Канал {channel} проанализирован, постов позавчера не было или все уже отправлены")
                    continue
                candidates.append(result)
                reports.append(f"✅ Канал {channel}: найден пост с {result['reactions']} реакциями")
            except Exception as e:
                error_msg = str(e)
                if "CHANNEL_PRIVATE" in error_msg:
                    reports.append(f"❌ Канал {channel}: недоступен (приватный)")
                elif "USERNAME_NOT_OCCUPIED" in error_msg:
                    reports.append(f"❌ Канал {channel}: не существует")
                else:
                    reports.append(f"❌ Канал {channel}: ошибка - {error_msg}")
        if not candidates:
            reports.append("\n⚠️ Нет постов для отправки")
            return [], reports
        candidates.sort(key=lambda x: (x['reactions'], x['views']), reverse=True)
        limit = self.config.get_setting('post_limit', 3)
        if limit == "all":
            limit = len(candidates)
        else:
            limit = min(int(limit), len(candidates))
        top = candidates[:limit]
        reports.append(f"\n📊 Отобрано {len(top)} постов из {len(candidates)} каналов")
        return top, reports
    
    def mark_as_posted(self, items: List[Dict]):
        for item in items:
            self.config.add_posted(
                channel_id=item['channel_id'],
                message_id=item['message_id'],
                channel_title=item['channel']
            )