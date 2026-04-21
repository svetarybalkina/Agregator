import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class BotHandler:
    def __init__(self, config_manager, parser, run_collection_callback=None):
        self.config = config_manager
        self.parser = parser
        self.run_collection_callback = run_collection_callback
        self.application = None
    
    def init_bot(self):
        token = self.config.get_setting('bot_token')
        if not token:
            raise ValueError("Не указан токен бота")
        self.application = Application.builder().token(token).build()
        self.application.add_handler(CommandHandler("start", self.cmd_start))
        self.application.add_handler(CommandHandler("add_channel", self.cmd_add_channel))
        self.application.add_handler(CommandHandler("remove_channel", self.cmd_remove_channel))
        self.application.add_handler(CommandHandler("list_channels", self.cmd_list_channels))
        self.application.add_handler(CommandHandler("set_limit", self.cmd_set_limit))
        self.application.add_handler(CommandHandler("set_time", self.cmd_set_time))
        self.application.add_handler(CommandHandler("set_proxy", self.cmd_set_proxy))
        self.application.add_handler(CommandHandler("run_now", self.cmd_run_now))
        self.application.add_handler(CommandHandler("status", self.cmd_status))
        return self.application
    
    def _check_admin(self, update: Update) -> bool:
        if not update or not update.effective_user:
            return False
        admin_ids = self.config.get_setting('admin_ids', [])
        user_id = update.effective_user.id
        if not admin_ids or admin_ids == [0]:
            self.config.set_setting('admin_ids', [user_id])
            return True
        return user_id in admin_ids
    
    async def cmd_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not update.message:
            return
        if not self._check_admin(update):
            await update.message.reply_text("⛔ У вас нет доступа.")
            return
        await update.message.reply_text(
            "🤖 Агрегатор каналов (веб-парсер)\n\n"
            "/add_channel @channel — добавить источник\n"
            "/remove_channel @channel — удалить источник\n"
            "/list_channels — список источников\n"
            "/set_limit N или all — сколько постов отбирать\n"
            "/set_time ЧЧ:ММ — время сбора\n"
            "/set_proxy url — настроить прокси (или 'none')\n"
            "/run_now — собрать и прислать ссылки сейчас\n"
            "/status — статус"
        )
    
    async def cmd_add_channel(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not update.message:
            return
        if not self._check_admin(update):
            return
        if not context.args:
            await update.message.reply_text("❌ Укажите канал: /add_channel @channelname")
            return
        channel = context.args[0]
        if not channel.startswith('@'):
            channel = '@' + channel
        try:
            if self.config.add_source_channel(channel):
                await update.message.reply_text(f"✅ Канал {channel} добавлен")
            else:
                await update.message.reply_text(f"⚠️ Уже в списке")
        except ValueError as e:
            await update.message.reply_text(f"❌ {e}")
    
    async def cmd_remove_channel(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not update.message:
            return
        if not self._check_admin(update):
            return
        if not context.args:
            await update.message.reply_text("❌ Укажите канал: /remove_channel @channelname")
            return
        channel = context.args[0]
        if not channel.startswith('@'):
            channel = '@' + channel
        if self.config.remove_source_channel(channel):
            await update.message.reply_text(f"✅ Канал {channel} удален")
        else:
            await update.message.reply_text(f"⚠️ Не найден")
    
    async def cmd_list_channels(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not update.message:
            return
        if not self._check_admin(update):
            return
        channels = self.config.get_setting('source_channels', [])
        text = "📋 Каналы-источники:\n" + "\n".join([f"• {ch}" for ch in channels]) if channels else "📋 Список пуст"
        await update.message.reply_text(text)
    
    async def cmd_set_limit(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not update.message:
            return
        if not self._check_admin(update):
            return
        if not context.args:
            await update.message.reply_text("❌ Укажите число или 'all': /set_limit 3")
            return
        limit = context.args[0]
        if limit.lower() == 'all':
            self.config.set_setting('post_limit', 'all')
            await update.message.reply_text("✅ Будем отбирать все посты")
        else:
            try:
                num = int(limit)
                if 1 <= num <= 10:
                    self.config.set_setting('post_limit', num)
                    await update.message.reply_text(f"✅ Лимит: {num}")
                else:
                    await update.message.reply_text("❌ От 1 до 10")
            except ValueError:
                await update.message.reply_text("❌ Число или 'all'")
    
    async def cmd_set_time(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not update.message:
            return
        if not self._check_admin(update):
            return
        if not context.args:
            await update.message.reply_text("❌ Укажите время: /set_time 11:00")
            return
        time_str = context.args[0]
        try:
            hour, minute = map(int, time_str.split(':'))
            if 0 <= hour < 24 and 0 <= minute < 60:
                self.config.set_setting('schedule_time', time_str)
                await update.message.reply_text(f"✅ Время сбора: {time_str}")
            else:
                await update.message.reply_text("❌ Неверное время")
        except ValueError:
            await update.message.reply_text("❌ Формат: ЧЧ:ММ")
    
    async def cmd_set_proxy(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not update.message:
            return
        if not self._check_admin(update):
            return
        if not context.args or context.args[0].lower() == 'none':
            self.config.set_setting('proxy', None)
            await update.message.reply_text("✅ Прокси удален")
            return
        proxy_url = context.args[0]
        self.config.set_setting('proxy', proxy_url)
        await update.message.reply_text(f"✅ Прокси установлен: {proxy_url}")
    
    async def cmd_run_now(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not update.message:
            return
        if not self._check_admin(update):
            return
        await update.message.reply_text("🚀 Собираю посты...")
        if self.run_collection_callback:
            await self.run_collection_callback()
    
    async def cmd_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not update.message:
            return
        if not self._check_admin(update):
            return
        channels = self.config.get_setting('source_channels', [])
        limit = self.config.get_setting('post_limit', 3)
        time_str = self.config.get_setting('schedule_time', '11:00')
        proxy = self.config.get_setting('proxy', 'не используется')
        history_count = len(self.config.posted_history)
        status = (
            f"📊 Статус:\n"
            f"Источников: {len(channels)}\n"
            f"Лимит: {limit}\n"
            f"Время сбора: {time_str}\n"
            f"Прокси: {proxy}\n"
            f"В истории: {history_count} постов\n\n"
            f"Отправьте /run_now для ручного сбора"
        )
        await update.message.reply_text(status)
    
    async def send_links(self, posts: list, reports: list):
        """Отправка списка ссылок админу"""
        admin_ids = self.config.get_setting('admin_ids', [])
        if not admin_ids or admin_ids == [0] or not self.application:
            return
        if not posts:
            text = "📭 Постов не найдено\n\n" + "\n".join(reports)
            await self.application.bot.send_message(admin_ids[0], text=text)
            return
        lines = ["📊 Топ-посты за позавчера:\n"]
        for i, post in enumerate(posts, 1):
            username = post['channel'].replace('@', '')
            url = f"https://t.me/{username}/{post['message_id']}"
            text_preview = post.get('text', '')[:100]
            lines.append(f"{i}. {post['channel_title']}")
            lines.append(f"   🔗 {url}")
            lines.append(f"   👁 {post['views']} просмотров")
            if text_preview:
                lines.append(f"   📝 {text_preview}...\n")
            else:
                lines.append("")
        lines.append("—")
        lines.append("\n".join(reports))
        text = "\n".join(lines)
        if len(text) > 4000:
            parts = [text[i:i+4000] for i in range(0, len(text), 4000)]
            for part in parts:
                await self.application.bot.send_message(admin_ids[0], text=part)
        else:
            await self.application.bot.send_message(admin_ids[0], text=text)