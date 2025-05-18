# run.py
import asyncio
import logging
from aiogram import Bot, Dispatcher

from app import config as app_config
from app.handlers import router as app_router
from app.database.gsheets_setup import ensure_google_sheets_setup
from app.database.requests import sync_privacy_cache, sync_catalog_cache

# Настройка базового логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(name)s - %(module)s.%(funcName)s:%(lineno)d - %(message)s',
    handlers=[
        logging.FileHandler('bot.log', encoding='utf-8'),
        logging.StreamHandler()  # Сохраняем вывод в консоль
    ]
)
logger = logging.getLogger(__name__)

async def main():
    logger.info("Загрузка конфигурации...")
    # Конфигурация загружается при импорте app_config

    # --- Проверка основных URI перед настройкой ---
    if not all([app_config.GSHEETS_USERS_URI, app_config.GSHEETS_CATEGORIES_URI, app_config.GSHEETS_ITEMS_URI]):
        logger.critical("Один или несколько основных URI для Google Sheets не определены. Проверьте .env файл. Настройка не будет выполнена.")
        return

    bot_token = app_config.TG_TOKEN
    if not bot_token:
        logger.critical("Токен бота TG_TOKEN не найден. Проверьте .env файл.")
        return

    # --- Инициализация структуры Google Sheets ---
    try:
        # Вызываем функцию настройки перед запуском бота
        await ensure_google_sheets_setup()
        # Синхронизируем кэш согласий с Google Sheets
        await sync_privacy_cache()
        # Синхронизируем кэш каталога
        await sync_catalog_cache()
    except Exception as e:
        # Логируем ошибку, но позволяем боту запуститься, если это некритично,
        # или прерываем, если настройка таблиц обязательна.
        # Для данного случая, если таблицы не настроены, бот скорее всего не сможет работать корректно.
        logger.error(f"Критическая ошибка во время настройки Google Sheets: {e}. "
                     "Бот может работать некорректно или не запуститься.", exc_info=True)
        # Если настройка таблиц критична, можно раскомментировать следующую строку:
        # return
    # ---------------------------------------------

    bot = Bot(token=bot_token)
    dp = Dispatcher()
    dp.include_router(app_router)

    logger.info("Бот запускается...")
    try:
        await dp.start_polling(bot)
    except Exception as e:
        logger.error(f"Ошибка при работе бота: {e}", exc_info=True)
    finally:
        logger.info("Закрытие сессии бота...")
        await bot.session.close()
        logger.info("Сессия бота закрыта.")

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info('Бот остановлен вручную.')
    except Exception as e:
        logger.critical(f"Критическая ошибка при запуске main(): {e}", exc_info=True)