# run.py
import asyncio
import logging
from aiogram import Bot, Dispatcher

from app import config as app_config
from app.handlers import router as app_router
from app.handlers_order import router as order_router
from app.database.gsheets_setup import ensure_google_sheets_setup
from app.database.requests import sync_privacy_cache, sync_catalog_cache
from app.background_tasks import background_tasks

# Настройка базового логирования
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(name)s - %(module)s.%(funcName)s:%(lineno)d - %(message)s",
    handlers=[
        logging.FileHandler("bot.log", encoding="utf-8"),
        logging.StreamHandler(),  # Сохраняем вывод в консоль
    ],
)
logger = logging.getLogger(__name__)


async def main():
    logger.info("Загрузка конфигурации...")
    # Конфигурация загружается при импорте app_config

    # --- Проверка основных URI перед настройкой ---
    if not all(
        [
            app_config.GSHEETS_USERS_URI,
            # app_config.GSHEETS_CATEGORIES_URI,
            app_config.GSHEETS_ITEMS_URI,
        ]
    ):
        logger.critical(
            "Один или несколько основных URI для Google Sheets не определены. Проверьте .env файл. Настройка не будет выполнена."
        )
        return

    bot_token = app_config.TG_TOKEN
    if not bot_token:
        logger.critical("Токен бота TG_TOKEN не найден. Проверьте .env файл.")
        return

    # --- Инициализация структуры Google Sheets и кеша ---
    max_retries = 3
    retry_delay = 5  # секунд

    for attempt in range(max_retries):
        try:
            # Вызываем функцию настройки перед запуском бота
            await ensure_google_sheets_setup()
            # Синхронизируем кэш согласий с Google Sheets
            await sync_privacy_cache()
            # Синхронизируем кэш каталога
            await sync_catalog_cache()
            logger.info(
                "Google Sheets setup and cache initialization completed successfully"
            )
            break
        except Exception as e:
            if attempt < max_retries - 1:
                logger.warning(
                    f"Attempt {attempt + 1}/{max_retries} failed: {e}. Retrying in {retry_delay} seconds..."
                )
                await asyncio.sleep(retry_delay)
            else:
                logger.error(
                    f"Failed to initialize Google Sheets and cache after {max_retries} attempts: {e}. "
                    "Bot may not function correctly.",
                    exc_info=True,
                )

    # ---------------------------------------------

    bot = Bot(token=bot_token)
    dp = Dispatcher()
    dp.include_router(app_router)
    dp.include_router(order_router)

    # Запускаем фоновые задачи
    await background_tasks.start()

    logger.info("Бот запускается...")
    try:
        await dp.start_polling(bot)
    except Exception as e:
        logger.error(f"Ошибка при работе бота: {e}", exc_info=True)
    finally:
        # Останавливаем фоновые задачи
        await background_tasks.stop()
        logger.info("Закрытие сессии бота...")
        await bot.session.close()
        logger.info("Сессия бота закрыта.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Бот остановлен вручную.")
    except Exception as e:
        logger.critical(f"Критическая ошибка при запуске main(): {e}", exc_info=True)
