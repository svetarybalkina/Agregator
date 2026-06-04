import asyncio
import logging
import sys
from datetime import datetime

from telegram import Update

from bot_handler import BotHandler
from config_manager import ConfigManager
from user_client import UserClient

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
    handlers=[
        logging.FileHandler("aggregator.log", encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
    force=True,
)
logger = logging.getLogger(__name__)


class AggregatorApp:
    def __init__(self):
        self.config = ConfigManager()
        self.user_client = UserClient(self.config)
        self.bot_handler = BotHandler(
            self.config,
            self.user_client,
            run_collection_callback=self.run_collection,
        )
        self.shutdown_event = asyncio.Event()
        self.collection_done_today = False
        self.collection_lock = asyncio.Lock()

    async def collection_task(self):
        """Ожидание времени сбора и запуск."""
        while not self.shutdown_event.is_set():
            try:
                now = datetime.now()
                target_time_str = self.config.get_setting("schedule_time", "11:00")
                target_hour, target_minute = map(int, target_time_str.split(":"))

                if now.hour == target_hour and now.minute == target_minute and not self.collection_done_today:
                    logger.info(f"Наступило время сбора ({target_time_str})")
                    await self.run_collection()
                    self.collection_done_today = True

                if now.hour == 0 and now.minute == 0:
                    self.collection_done_today = False

            except Exception as e:
                logger.error(f"Ошибка collection_task: {e}", exc_info=True)

            try:
                await asyncio.wait_for(self.shutdown_event.wait(), timeout=30)
            except asyncio.TimeoutError:
                pass

    async def run_collection(self):
        """Сбор активной подборки и отправка отчета в бот."""
        if self.collection_lock.locked():
            await self.bot_handler.send_notification("Сбор уже выполняется. Дождитесь завершения текущего запуска.")
            return

        async with self.collection_lock:
            try:
                active = self.config.get_active_collection_name()
                posts, reports = await self.user_client.collect_posts()

                if posts:
                    self.user_client.mark_as_posted(posts)

                report_text = f"Подборка: {active}\n\n" + "\n".join(reports)
                await self.bot_handler.send_notification(report_text)

            except Exception as e:
                error_msg = f"Ошибка: {str(e)}"
                logger.error(error_msg, exc_info=True)
                await self.bot_handler.send_notification(error_msg)
            finally:
                try:
                    await self.user_client.disconnect()
                except Exception as e:
                    logger.warning(f"Ошибка отключения: {e}")

    async def check_missed_collection(self):
        """Проверка пропущенного сбора при старте."""
        now = datetime.now()
        target_time_str = self.config.get_setting("schedule_time", "11:00")
        target_hour, target_minute = map(int, target_time_str.split(":"))

        if (now.hour > target_hour or (now.hour == target_hour and now.minute > target_minute)) and not self.collection_done_today:
            logger.info("Обнаружен пропущенный запуск. Выполняю...")
            await self.run_collection()
            self.collection_done_today = True

    async def run(self):
        """Основной метод запуска."""
        logger.info("=" * 50)
        logger.info("Запуск агрегатора (система подборок)")
        logger.info("Python: " + sys.version)
        logger.info("=" * 50)

        active = self.config.get_active_collection_name()
        channels = self.config.get_active_channels()
        all_collections = self.config.get_all_collections()

        logger.info(f"Всего подборок: {len(all_collections)}")
        for name, chs in all_collections.items():
            marker = " *" if name == active else ""
            logger.info(f"  {name}{marker}: {len(chs)} каналов")
        logger.info(f"Активная подборка: {active} ({len(channels)} каналов)")

        if not channels:
            logger.warning("ВНИМАНИЕ: Активная подборка пуста! Добавьте каналы в collections.json")

        application = self.bot_handler.init_bot()
        await application.initialize()
        await application.start()
        logger.info("Бот инициализирован")

        polling_task = asyncio.create_task(
            application.updater.start_polling(allowed_updates=Update.ALL_TYPES)
        )
        collection_task = asyncio.create_task(self.collection_task())
        missed_task = asyncio.create_task(self.check_missed_collection())

        target_time = self.config.get_setting("schedule_time", "11:00")
        logger.info(f"Скрипт работает. Анализ запланирован на {target_time}")
        logger.info("Нажмите Ctrl+C для остановки")

        try:
            await self.shutdown_event.wait()
        except KeyboardInterrupt:
            logger.info("Получен сигнал остановки...")

        logger.info("Остановка приложения...")
        self.shutdown_event.set()

        collection_task.cancel()
        polling_task.cancel()
        missed_task.cancel()

        for task in (collection_task, polling_task, missed_task):
            try:
                await task
            except asyncio.CancelledError:
                pass

        await application.stop()
        await application.shutdown()
        logger.info("Приложение остановлено")


if __name__ == "__main__":
    app = AggregatorApp()
    try:
        asyncio.run(app.run())
    except KeyboardInterrupt:
        logger.info("Остановлено пользователем")
        sys.exit(0)
