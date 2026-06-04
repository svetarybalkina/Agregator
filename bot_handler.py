import logging
import os
from contextlib import contextmanager

import httpx
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
from telegram.request import HTTPXRequest

logger = logging.getLogger(__name__)

PROXY_ENV_VARS = (
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "ALL_PROXY",
    "http_proxy",
    "https_proxy",
    "all_proxy",
)


@contextmanager
def without_proxy_env():
    saved = {name: os.environ.get(name) for name in PROXY_ENV_VARS}
    try:
        for name in PROXY_ENV_VARS:
            os.environ.pop(name, None)
        yield
    finally:
        for name, value in saved.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value


class BotHandler:
    def __init__(self, config_manager, user_client, run_collection_callback=None):
        self.config = config_manager
        self.user_client = user_client
        self.run_collection_callback = run_collection_callback
        self.application = None

    def init_bot(self):
        token = self.config.get_setting("bot_token")
        if not token:
            raise ValueError("Не указан токен бота")
        with without_proxy_env():
            self.application = (
                Application.builder()
                .token(token)
                .request(NoProxyHTTPXRequest())
                .get_updates_request(NoProxyHTTPXRequest())
                .build()
            )
        self.application.add_handler(CommandHandler("start", self.cmd_start))
        self.application.add_handler(CommandHandler("podborki", self.cmd_collections))
        self.application.add_handler(CommandHandler("tekushaya_podborka", self.cmd_current))
        self.application.add_handler(CommandHandler("run_now", self.cmd_run_now))
        self.application.add_handler(CommandHandler("status", self.cmd_status))
        self.application.add_handler(CommandHandler("chat_id", self.cmd_chat_id))
        return self.application

    def _check_admin(self, update: Update) -> bool:
        admin_ids = self.config.get_setting("admin_ids", [])
        user_id = update.effective_user.id
        if not admin_ids or admin_ids == [0]:
            self.config.set_setting("admin_ids", [user_id])
            return True
        return user_id in admin_ids

    async def cmd_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self._check_admin(update):
            await update.message.reply_text("У вас нет доступа к этому боту.")
            return
        await update.message.reply_text(
            "Агрегатор каналов (система подборок)\n\n"
            "Доступные команды:\n"
            "/podborki - список подборок\n"
            "/tekushaya_podborka - текущая активная подборка\n"
            "/run_now - запустить сбор текущей подборки\n"
            "/status - статус системы\n\n"
            "/chat_id - показать ID текущего чата\n"
            "Подборки хранятся в файле collections.json."
        )

    async def cmd_collections(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self._check_admin(update):
            return
        collections = self.config.get_all_collections()
        active = self.config.get_active_collection_name()
        lines = ["Доступные подборки:\n"]
        for name, channels in collections.items():
            marker = " *" if name == active else ""
            lines.append(f"- {name}{marker} - {len(channels)} каналов")
        lines.append(f"\nАктивная: {active}")
        await update.message.reply_text("\n".join(lines))

    async def cmd_current(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self._check_admin(update):
            return
        active = self.config.get_active_collection_name()
        channels = self.config.get_active_channels()
        await update.message.reply_text(
            f"Текущая подборка: {active}\n"
            f"Каналов: {len(channels)}\n"
            + ("\n".join([f"- {ch}" for ch in channels]) if channels else "(пусто)")
        )

    async def cmd_run_now(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self._check_admin(update):
            return
        active = self.config.get_active_collection_name()
        await update.message.reply_text(f"Запускаю сбор подборки '{active}'...")
        if self.run_collection_callback:
            await self.run_collection_callback()

    async def cmd_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self._check_admin(update):
            return
        active = self.config.get_active_collection_name()
        channels = self.config.get_active_channels()
        limit = self.config.get_setting("post_limit", 3)
        time_str = self.config.get_setting("schedule_time", "11:00")
        history = self.config.get_posted_history()
        status = (
            "Статус:\n\n"
            f"Текущая подборка: {active}\n"
            f"Каналов: {len(channels)}\n"
            f"Лимит постов: {limit}\n"
            f"Время запуска: {time_str}\n"
            f"Отправлено в истории: {len(history)}"
        )
        await update.message.reply_text(status)

    async def cmd_chat_id(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self._check_admin(update):
            return
        await update.message.reply_text(
            f"Your ID: {update.effective_user.id}\n"
            f"Current chat ID: {update.effective_chat.id}"
        )

    async def send_notification(self, message: str):
        admin_ids = self.config.get_setting("admin_ids", [])
        target_chat_id = self.config.get_setting("report_chat_id")
        if target_chat_id is None and admin_ids:
            target_chat_id = admin_ids[0]
        if target_chat_id is not None and self.application:
            try:
                for chunk in self._split_message(message):
                    await self.application.bot.send_message(target_chat_id, chunk)
            except Exception as e:
                logger.error(f"Не удалось отправить уведомление: {e}")

    def _split_message(self, message: str, limit: int = 3900):
        if len(message) <= limit:
            return [message]
        chunks = []
        current = []
        current_len = 0
        for line in message.splitlines():
            extra = len(line) + 1
            if current and current_len + extra > limit:
                chunks.append("\n".join(current))
                current = []
                current_len = 0
            current.append(line)
            current_len += extra
        if current:
            chunks.append("\n".join(current))
        return chunks


class NoProxyHTTPXRequest(HTTPXRequest):
    def _build_client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(**self._client_kwargs, trust_env=False)
