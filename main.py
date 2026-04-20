import asyncio
import logging
import sys
from datetime import datetime, timedelta
from config_manager import ConfigManager
from user_client import UserClient
from bot_handler import BotHandler
from telegram import Update

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    handlers=[
        logging.FileHandler("aggregator.log", encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

class AggregatorApp:
    def __init__(self):
        self.config = ConfigManager()
        self.user_client = UserClient(self.config)
        self.bot_handler = BotHandler(
            self.config,
            self.user_client,
            run_collection_callback=self.run_collection
        )
        self.shutdown_event = asyncio.Event()
        self.collection_done_today = False
    
    async def collection_task(self):
        while not self.shutdown_event.is_set():
            try:
                now = datetime.now()
                target_time_str = self.config.get_setting('schedule_time', '11:00')
                target_hour, target_minute = map(int, target_time_str.split(':'))
                if now.hour == target_hour and now.minute == 0 and not self.collection_done_today:
                    logger.info(f"Время сбора ({target_time_str})")
                    await self.run_collection()
                    self.collection_done_today = True
                if now.hour == target_hour and now.minute > 0:
                    self.collection_done_today = False
                if now.hour == 0 and now.minute == 0:
                    self.collection_done_today = False
            except Exception as e:
                logger.error(f"Ошибка collection_task: {e}", exc_info=True)
            try:
                await asyncio.wait_for(self.shutdown_event.wait(), timeout=30)
            except asyncio.TimeoutError:
                pass
    
    async def run_collection(self):
        try:
            posts, reports = await self.user_client.collect_posts()
            if posts:
                self.user_client.mark_as_posted(posts)
            await self.bot_handler.send_links(posts, reports)
        except Exception as e:
            error_msg = f"❌ Ошибка: {str(e)}"
            logger.error(error_msg, exc_info=True)
            await self.bot_handler.send_links([], [error_msg])
    
    async def check_missed_collection(self):
        now = datetime.now()
        target_time_str = self.config.get_setting('schedule_time', '11:00')
        target_hour, target_minute = map(int, target_time_str.split(':'))
        if (now.hour > target_hour or (now.hour == target_hour and now.minute > 0)) and not self.collection_done_today:
            today_start = datetime(now.year, now.month, now.day, 0, 0, 0)
            recent_posts = []
            for h in self.config.posted_history:
                try:
                    post_date = datetime.fromisoformat(h['date'])
                    if post_date.tzinfo is not None:
                        post_date = post_date.replace(tzinfo=None)
                    if post_date > today_start:
                        recent_posts.append(h)
                except (ValueError, KeyError):
                    continue
            if not recent_posts:
                logger.info("Пропущенный сбор. Выполняю...")
                await self.run_collection()
                self.collection_done_today = True
    
    async def run(self):
        logger.info("=" * 50)
        logger.info("Запуск агрегатора (режим ссылок)")
        logger.info("Python: " + sys.version)
        logger.info("=" * 50)
        await self.user_client.connect()
        logger.info("Telethon подключен")
        application = self.bot_handler.init_bot()
        await application.initialize()
        await application.start()
        logger.info("Бот инициализирован")
        await self.check_missed_collection()
        collection_task = asyncio.create_task(self.collection_task())
        polling_task = asyncio.create_task(
            application.updater.start_polling(allowed_updates=Update.ALL_TYPES)
        )
        target_time = self.config.get_setting('schedule_time', '11:00')
        logger.info(f"Работает. Сбор и отправка ссылок: {target_time}. Ctrl+C — остановить.")
        try:
            await self.shutdown_event.wait()
        except KeyboardInterrupt:
            logger.info("Остановка...")
        logger.info("Завершение работы...")
        polling_task.cancel()
        collection_task.cancel()
        try:
            await polling_task
        except asyncio.CancelledError:
            pass
        try:
            await collection_task
        except asyncio.CancelledError:
            pass
        await application.stop()
        await application.shutdown()
        await self.user_client.disconnect()
        logger.info("Остановлено")

if __name__ == "__main__":
    app = AggregatorApp()
    try:
        asyncio.run(app.run())
    except KeyboardInterrupt:
        logger.info("Остановлено пользователем")
        sys.exit(0)