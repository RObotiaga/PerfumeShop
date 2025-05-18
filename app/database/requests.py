# app/database/requests.py
import asyncio
from typing import List, Optional, Dict, Any
from shillelagh.backends.apsw.db import connect as shillelagh_connect
import logging

from app import config as app_config
from app.database.gsheets_setup import get_sheet_gid
from app.database.cache import privacy_cache, catalog_cache

logger = logging.getLogger(__name__)

def _get_sheet_uri_with_gid(uri: str) -> str:
    """Преобразует URI с именем листа в URI с gid."""
    # Удаляем /edit и все после него
    base_uri = uri.split('/edit')[0]
    
    gid = get_sheet_gid(uri)
    if gid is None:
        logger.warning(f"GID не найден для URI {uri}, используем оригинальный URI")
        return base_uri
    
    # Добавляем gid к базовому URI
    return f"{base_uri}#gid={gid}"

# --- Вспомогательная функция для подключения к Shillelagh ---
def get_gsheets_connection():
    """Создает и возвращает соединение Shillelagh с Google Sheets."""
    adapter_kwargs = {"gsheetsapi": {}}
    # Приоритет аутентификации: Service Account File > Access Token > App Default
    if app_config.GSHEETS_SERVICE_ACCOUNT_FILE:
        adapter_kwargs["gsheetsapi"]["service_account_file"] = app_config.GSHEETS_SERVICE_ACCOUNT_FILE
        if app_config.GSHEETS_SUBJECT_EMAIL:
            adapter_kwargs["gsheetsapi"]["subject"] = app_config.GSHEETS_SUBJECT_EMAIL
    elif app_config.GSHEETS_ACCESS_TOKEN:
        adapter_kwargs["gsheetsapi"]["access_token"] = app_config.GSHEETS_ACCESS_TOKEN
    elif app_config.GSHEETS_USE_APP_DEFAULT_CREDENTIALS:
        adapter_kwargs["gsheetsapi"]["app_default_credentials"] = True
    else:
        logger.warning("GSHEETS: No specific authentication method configured. "
                       "Shillelagh will attempt to use Application Default Credentials "
                       "or operate in public-only mode.")

    try:
        # gsheets_prefetch можно использовать для предзагрузки метаданных таблиц
        # Это может ускорить первые запросы, но замедлить старт.
        # Для динамических таблиц можно установить в False или не указывать.
        connection = shillelagh_connect(
            ":memory:",
            adapter_kwargs=adapter_kwargs,
            # Пример prefetch, если URIs точно известны и не меняются часто:
            # gsheets_prefetch=[
            #     app_config.GSHEETS_USERS_URI,
            #     app_config.GSHEETS_CATEGORIES_URI,
            #     app_config.GSHEETS_ITEMS_URI
            # ]
        )
        return connection
    except Exception as e:
        logger.error(f"Failed to connect to Shillelagh: {e}", exc_info=True)
        raise # Перебрасываем исключение, чтобы вызывающий код мог его обработать

# --- Обертка для выполнения синхронных вызовов Shillelagh в асинхронном коде ---
async def run_shillelagh_query(query: str, params: tuple = (), fetch_one: bool = False, commit: bool = False):
    """Выполняет SQL-запрос к Google Sheets через Shillelagh в отдельном потоке."""
    def _execute():
        conn = None
        try:
            conn = get_gsheets_connection()
            cursor = conn.cursor()
            logger.debug(f"Executing Shillelagh query: {query} with params: {params}")
            cursor.execute(query, params)
            if commit:
                conn.commit()
                return None # Для INSERT/UPDATE/DELETE обычно ничего не возвращаем
            if fetch_one:
                return cursor.fetchone()
            return cursor.fetchall()
        except Exception as e:
            logger.error(f"Unexpected error during Shillelagh query: {e}. Query: {query}, Params: {params}", exc_info=True)
            raise
        finally:
            if conn:
                conn.close()

    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, _execute)


# --- USER OPERATIONS ---
async def set_user(tg_id: int) -> None:
    """Добавляет нового пользователя, если его нет."""
    uri = _get_sheet_uri_with_gid(app_config.GSHEETS_USERS_URI)
    check_query = f'SELECT "{app_config.COL_USER_TG_ID}" FROM "{uri}" WHERE "{app_config.COL_USER_TG_ID}" = ?'
    user_exists = await run_shillelagh_query(check_query, (tg_id,), fetch_one=True)

    if not user_exists:
        insert_query = f'INSERT INTO "{uri}" ("{app_config.COL_USER_TG_ID}", "{app_config.COL_USER_PRIVACY_ACCEPTED}") VALUES (?, ?)'
        await run_shillelagh_query(insert_query, (tg_id, False), commit=True)
        logger.info(f"User {tg_id} added to Google Sheet.")
    else:
        logger.info(f"User {tg_id} already exists in Google Sheet.")

async def get_user_privacy_status(tg_id: int) -> bool:
    """Получает статус согласия пользователя с политикой конфиденциальности."""
    # Сначала проверяем кэш
    if privacy_cache.is_initialized():
        return privacy_cache.is_accepted(tg_id)
    
    # Если кэш не инициализирован, получаем данные из Google Sheets
    uri = _get_sheet_uri_with_gid(app_config.GSHEETS_USERS_URI)
    query = f'SELECT "{app_config.COL_USER_PRIVACY_ACCEPTED}" FROM "{uri}" WHERE "{app_config.COL_USER_TG_ID}" = ?'
    result = await run_shillelagh_query(query, (tg_id,), fetch_one=True)
    is_accepted = bool(result[0]) if result and result[0] is not None else False
    
    # Если пользователь согласился, добавляем его в кэш
    if is_accepted:
        privacy_cache.add_user(tg_id)
    
    return is_accepted

async def accept_privacy_policy(tg_id: int) -> None:
    """Обновляет статус согласия пользователя с политикой конфиденциальности."""
    uri = _get_sheet_uri_with_gid(app_config.GSHEETS_USERS_URI)
    query = f'UPDATE "{uri}" SET "{app_config.COL_USER_PRIVACY_ACCEPTED}" = ? WHERE "{app_config.COL_USER_TG_ID}" = ?'
    await run_shillelagh_query(query, (True, tg_id), commit=True)
    # Добавляем пользователя в кэш
    privacy_cache.add_user(tg_id)
    logger.info(f"User {tg_id} accepted privacy policy.")

async def sync_privacy_cache() -> None:
    """Синхронизирует кэш с данными из Google Sheets."""
    uri = _get_sheet_uri_with_gid(app_config.GSHEETS_USERS_URI)
    query = f'SELECT "{app_config.COL_USER_TG_ID}" FROM "{uri}" WHERE "{app_config.COL_USER_PRIVACY_ACCEPTED}" = ?'
    results = await run_shillelagh_query(query, (True,))
    
    # Создаем множество ID пользователей, согласившихся с политикой
    accepted_users = {int(row[0]) for row in results if row[0] is not None}
    
    # Инициализируем кэш
    privacy_cache.initialize(accepted_users)
    logger.info(f"Privacy cache synchronized with {len(accepted_users)} users")

# --- CATEGORY OPERATIONS ---
CategoryData = Dict[str, Any]

async def get_categories() -> List[CategoryData]:
    """Получает список категорий."""
    # Проверяем кэш
    if catalog_cache.is_initialized() and not catalog_cache.needs_update():
        return catalog_cache.get_categories()

    if not app_config.GSHEETS_CATEGORIES_URI or not app_config.COL_CATEGORY_NAME:
        logger.error("GSHEETS_CATEGORIES_URI или COL_CATEGORY_NAME не настроены.")
        return []

    uri = _get_sheet_uri_with_gid(app_config.GSHEETS_CATEGORIES_URI)
    category_col_name = app_config.COL_CATEGORY_NAME

    logger.info(f"Fetching categories from URI: '{uri}' using column: '{category_col_name}'")

    query = f'SELECT DISTINCT "{category_col_name}" FROM "{uri}"'
    logger.debug(f"Executing query for categories: {query}")

    try:
        rows = await run_shillelagh_query(query)
        logger.info(f"Raw rows received from Shillelagh for categories: {rows}")

        categories = []
        if rows:
            for row_tuple in rows:
                if row_tuple and row_tuple[0] is not None:
                    category_value = str(row_tuple[0]).strip()
                    if not category_value:
                        continue
                    categories.append({"id": category_value, "name": category_value})

        logger.info(f"Processed categories: {categories}")
        return categories
    except Exception as e:
        logger.error(f"Error fetching or processing categories: {e}", exc_info=True)
        return []

# --- ITEM OPERATIONS ---
ItemData = Dict[str, Any]

async def get_items_by_category(category_name: str) -> List[ItemData]:
    """Получает товары по имени категории."""
    # Проверяем кэш
    if catalog_cache.is_initialized() and not catalog_cache.needs_update():
        return catalog_cache.get_items_by_category(category_name)

    uri = _get_sheet_uri_with_gid(app_config.GSHEETS_ITEMS_URI)
    query = f"""
        SELECT
            "{app_config.COL_ITEM_ID}",
            "{app_config.COL_ITEM_CATEGORY_NAME}",
            "{app_config.COL_ITEM_NAME}",
            "{app_config.COL_ITEM_DESCRIPTION}",
            "{app_config.COL_ITEM_PRICE}",
            "{app_config.COL_ITEM_IMAGE_URL}",
            "{app_config.COL_ITEM_UNIT}",
            "{app_config.COL_ITEM_QUANTITY}",
            "{app_config.COL_ITEM_STATUS}",
            "{app_config.COL_ITEM_ORDER_STEPS}"
        FROM "{uri}"
        WHERE "{app_config.COL_ITEM_CATEGORY_NAME}" = ?
        AND "{app_config.COL_ITEM_STATUS}" != ?
    """
    rows = await run_shillelagh_query(query, (category_name, app_config.ITEM_STATUS_UNAVAILABLE))
    items = []
    for row in rows:
        try:
            # Парсим шаги заказа для товаров в Мл
            order_steps = []
            if row[9] and str(row[6]).strip() == app_config.ITEM_UNIT_ML:
                try:
                    # Удаляем все пробелы перед парсингом
                    steps_str = str(row[9]).replace(" ", "")
                    order_steps = [float(step.strip()) for step in steps_str.split(',') if step.strip()]
                    print(f"Parsed order steps: {order_steps}", 'debug_parsed_steps')
                except ValueError:
                    logger.warning(f"Invalid order steps format for item {row[0]}: {row[9]}")
                    order_steps = []

            items.append({
                "id": str(row[0]),
                "category_name": str(row[1]),
                "name": str(row[2]),
                "description": str(row[3]),
                "price": float(row[4]) if row[4] is not None else 0.0,
                "image_url": str(row[5]) if row[5] is not None else None,
                "unit": str(row[6]) if row[6] is not None else app_config.ITEM_UNIT_PCS,
                "quantity": int(row[7]) if row[7] is not None else 0,
                "status": str(row[8]) if row[8] is not None else app_config.ITEM_STATUS_AVAILABLE,
                "order_steps": order_steps
            })
        except (TypeError, ValueError) as e:
            logger.error(f"Error parsing item data for category '{category_name}': {row} - {e}")
            continue

    logger.info(f"Fetched {len(items)} items for category '{category_name}'.")
    return items

async def get_item(item_id: str) -> Optional[ItemData]:
    """Получает информацию о товаре по его ID."""
    # Проверяем кэш
    # if catalog_cache.is_initialized() and not catalog_cache.needs_update():
    #     return catalog_cache.get_item(item_id)

    uri = _get_sheet_uri_with_gid(app_config.GSHEETS_ITEMS_URI)
    print(f"Using URI: {uri}", 'debug_uri')
    
    # Сначала проверим структуру таблицы
    check_query = f'SELECT * FROM "{uri}" LIMIT 1'
    print(f"Check query: {check_query}", 'debug_check_query')
    check_result = await run_shillelagh_query(check_query)
    print(f"Table structure: {check_result}", 'debug_table_structure')
    
    # Основной запрос
    query = f"""
        SELECT
            "{app_config.COL_ITEM_ID}",
            "{app_config.COL_ITEM_CATEGORY_NAME}",
            "{app_config.COL_ITEM_NAME}",
            "{app_config.COL_ITEM_DESCRIPTION}",
            "{app_config.COL_ITEM_PRICE}",
            "{app_config.COL_ITEM_IMAGE_URL}",
            "{app_config.COL_ITEM_UNIT}",
            "{app_config.COL_ITEM_QUANTITY}",
            "{app_config.COL_ITEM_STATUS}",
            "{app_config.COL_ITEM_ORDER_STEPS}"
        FROM "{uri}"
        WHERE A = ?
    """
    print(f"Using query: {query}", 'debug_query')
    print(f"Using item_id: {item_id}", 'debug_item_id')
    print(f"Column names: {[app_config.COL_ITEM_ID, app_config.COL_ITEM_CATEGORY_NAME, app_config.COL_ITEM_NAME, app_config.COL_ITEM_DESCRIPTION, app_config.COL_ITEM_PRICE, app_config.COL_ITEM_IMAGE_URL, app_config.COL_ITEM_UNIT, app_config.COL_ITEM_QUANTITY, app_config.COL_ITEM_STATUS, app_config.COL_ITEM_ORDER_STEPS]}", 'debug_columns')
    
    row = await run_shillelagh_query(query, (item_id,), fetch_one=True)
    print(row, 'testiksearch')
    print(f"Raw order_steps value: {row[9] if row else None}", 'debug_order_steps')
    print(f"Raw unit value: {row[6] if row else None}", 'debug_unit')
    if row:
        try:
            # Парсим шаги заказа для товаров в Мл
            order_steps = []
            if row[9] and str(row[6]).strip() == app_config.ITEM_UNIT_ML:
                try:
                    # Удаляем все пробелы перед парсингом
                    steps_str = str(row[9]).replace(" ", "")
                    order_steps = [float(step.strip()) for step in steps_str.split(',') if step.strip()]
                    print(f"Parsed order steps: {order_steps}", 'debug_parsed_steps')
                except ValueError:
                    logger.warning(f"Invalid order steps format for item {row[0]}: {row[9]}")
                    order_steps = []

            item = {
                "id": str(row[0]),
                "category_name": str(row[1]),
                "name": str(row[2]),
                "description": str(row[3]),
                "price": float(row[4]) if row[4] is not None else 0.0,
                "image_url": str(row[5]) if row[5] is not None else None,
                "unit": str(row[6]) if row[6] is not None else app_config.ITEM_UNIT_PCS,
                "quantity": int(row[7]) if row[7] is not None else 0,
                "status": str(row[8]) if row[8] is not None else app_config.ITEM_STATUS_AVAILABLE,
                "order_steps": order_steps
            }
            logger.info(f"Fetched item with id '{item_id}'.")
            return item
        except (TypeError, ValueError) as e:
            logger.error(f"Error parsing item data for item_id '{item_id}': {row} - {e}")
            return None
    logger.warning(f"Item with id '{item_id}' not found.")
    return None

async def sync_catalog_cache() -> None:
    """Синхронизирует кэш каталога с данными из Google Sheets."""
    # Получаем все категории
    categories = await get_categories()
    
    # Получаем товары для каждой категории
    items_by_category = {}
    for category in categories:
        category_name = category['name']
        items = await get_items_by_category(category_name)
        items_by_category[category_name] = items
    
    # Обновляем кэш
    catalog_cache.update(categories, items_by_category)
    logger.info("Catalog cache synchronized")