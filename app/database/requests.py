# app/database/requests.py
import asyncio
from typing import List, Optional, Dict, Any, Set, Tuple
from shillelagh.backends.apsw.db import connect as shillelagh_connect
import logging
from datetime import datetime
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
import json

from app import config as app_config
from app.database.gsheets_setup import get_sheet_gid
from app.database.cache import privacy_cache, catalog_cache, cart_cache

logger = logging.getLogger(__name__)


def _get_sheet_uri_with_gid(uri: str) -> str:
    """Преобразует URI с именем листа в URI с gid."""
    # Удаляем /edit и все после него
    base_uri = uri.split("/edit")[0]

    gid = get_sheet_gid(uri)
    if gid is None:
        logger.warning(f"GID не найден для URI {uri}, используем оригинальный URI")
        return base_uri  # Возвращаем base_uri, а не оригинальный uri, чтобы убрать /edit...#sheet=...

    # Добавляем gid к базовому URI
    return f"{base_uri}#gid={gid}"


# --- Вспомогательная функция для подключения к Shillelagh ---
def get_gsheets_connection():
    """Создает и возвращает соединение Shillelagh с Google Sheets."""
    adapter_kwargs = {"gsheetsapi": {}}
    # Приоритет аутентификации: Service Account File > Access Token > App Default
    if app_config.GSHEETS_SERVICE_ACCOUNT_FILE:
        adapter_kwargs["gsheetsapi"][
            "service_account_file"
        ] = app_config.GSHEETS_SERVICE_ACCOUNT_FILE
        if app_config.GSHEETS_SUBJECT_EMAIL:
            adapter_kwargs["gsheetsapi"]["subject"] = app_config.GSHEETS_SUBJECT_EMAIL
    elif app_config.GSHEETS_ACCESS_TOKEN:
        adapter_kwargs["gsheetsapi"]["access_token"] = app_config.GSHEETS_ACCESS_TOKEN
    elif app_config.GSHEETS_USE_APP_DEFAULT_CREDENTIALS:
        adapter_kwargs["gsheetsapi"]["app_default_credentials"] = True
    else:
        logger.warning(
            "GSHEETS: No specific authentication method configured. "
            "Shillelagh will attempt to use Application Default Credentials "
            "or operate in public-only mode."
        )

    try:
        connection = shillelagh_connect(
            ":memory:",
            adapter_kwargs=adapter_kwargs,
        )
        return connection
    except Exception as e:
        logger.error(f"Failed to connect to Shillelagh: {e}", exc_info=True)
        raise


async def run_shillelagh_query(
    query: str, params: tuple = (), fetch_one: bool = False, commit: bool = False
):
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
                return None
            if fetch_one:
                return cursor.fetchone()
            return cursor.fetchall()
        except Exception as e:
            logger.error(
                f"Unexpected error during Shillelagh query: {e}. Query: {query}, Params: {params}",
                exc_info=True,
            )
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
    if privacy_cache.is_initialized():
        return privacy_cache.is_accepted(tg_id)

    uri = _get_sheet_uri_with_gid(app_config.GSHEETS_USERS_URI)
    query = f'SELECT "{app_config.COL_USER_PRIVACY_ACCEPTED}" FROM "{uri}" WHERE "{app_config.COL_USER_TG_ID}" = ?'
    result = await run_shillelagh_query(query, (tg_id,), fetch_one=True)
    is_accepted = bool(result[0]) if result and result[0] is not None else False

    if is_accepted:
        privacy_cache.add_user(tg_id)

    return is_accepted


async def accept_privacy_policy(tg_id: int) -> None:
    """Обновляет статус согласия пользователя с политикой конфиденциальности."""
    uri = _get_sheet_uri_with_gid(app_config.GSHEETS_USERS_URI)
    query = f'UPDATE "{uri}" SET "{app_config.COL_USER_PRIVACY_ACCEPTED}" = ? WHERE "{app_config.COL_USER_TG_ID}" = ?'
    await run_shillelagh_query(query, (True, tg_id), commit=True)
    privacy_cache.add_user(tg_id)
    logger.info(f"User {tg_id} accepted privacy policy.")


async def sync_privacy_cache() -> None:
    """Синхронизирует кэш конфиденциальности с Google Sheets."""
    try:
        # Получаем текущие данные из Google Sheets
        current_data = await get_all_users()
        current_users = {
            user["user_id"] for user in current_data if user.get("privacy_accepted")
        }

        if not privacy_cache.is_initialized():
            # Если кэш не инициализирован, инициализируем его
            privacy_cache.initialize(current_users)
            return

        # Получаем текущие данные из кэша
        cached_users = privacy_cache.get_all_accepted_users()

        # Находим разницу
        new_users = current_users - cached_users
        removed_users = cached_users - current_users

        if new_users or removed_users:
            # Обновляем кэш частично
            privacy_cache.update_partial(new_users, removed_users)
            logger.info(
                f"Privacy cache synchronized: added {len(new_users)} users, removed {len(removed_users)} users"
            )
        else:
            logger.info("Privacy cache is up to date")

    except Exception as e:
        logger.error(f"Error synchronizing privacy cache: {e}", exc_info=True)
        raise


# --- CATEGORY OPERATIONS ---
CategoryData = Dict[str, Any]


async def get_categories() -> List[CategoryData]:
    """Получает список категорий."""
    if catalog_cache.is_initialized() and not catalog_cache.needs_update():
        return catalog_cache.get_categories()

    if not app_config.GSHEETS_CATEGORIES_URI or not app_config.COL_CATEGORY_NAME:
        logger.error("GSHEETS_CATEGORIES_URI или COL_CATEGORY_NAME не настроены.")
        return []

    uri = _get_sheet_uri_with_gid(app_config.GSHEETS_CATEGORIES_URI)
    category_col_name = app_config.COL_CATEGORY_NAME

    logger.info(
        f"Fetching categories from URI: '{uri}' using column: '{category_col_name}'"
    )

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


def _parse_item_row(row: tuple, item_id_for_log: str) -> Optional[ItemData]:
    """Вспомогательная функция для парсинга строки данных товара."""
    try:
        # Определяем единицу измерения
        raw_unit_val = str(row[6]).strip() if row[6] is not None else ""
        item_unit = app_config.ITEM_UNIT_PCS  # По умолчанию Шт
        if raw_unit_val == app_config.ITEM_UNIT_ML:
            item_unit = app_config.ITEM_UNIT_ML
        elif raw_unit_val == app_config.ITEM_UNIT_PCS:
            item_unit = app_config.ITEM_UNIT_PCS
        elif raw_unit_val:  # Если не пусто и не распознано
            logger.warning(
                f"Unrecognized unit '{raw_unit_val}' for item {item_id_for_log}. Defaulting to PCS."
            )

        # Парсим шаги заказа для товаров в Мл
        order_steps_list = []
        if (
            item_unit == app_config.ITEM_UNIT_ML and row[9] is not None
        ):  # row[9] это COL_ITEM_ORDER_STEPS
            raw_steps_str = str(row[9]).strip()
            if raw_steps_str:
                steps_str_no_space = raw_steps_str.replace(" ", "")
                parsed_step_strings = [
                    s.strip() for s in steps_str_no_space.split(",") if s.strip()
                ]

                for step_val_str in parsed_step_strings:
                    try:
                        order_steps_list.append(float(step_val_str))
                    except ValueError:
                        logger.warning(
                            f"Invalid numeric value for step '{step_val_str}' in order_steps '{raw_steps_str}' for item {item_id_for_log}. Skipping this step."
                        )

                if (
                    not order_steps_list and parsed_step_strings
                ):  # Если были строки, но ни одна не стала числом
                    logger.warning(
                        f"Order steps string '{raw_steps_str}' for ML item {item_id_for_log} contained no valid numbers. order_steps will be empty."
                    )
            # Если raw_steps_str пуст, order_steps_list останется [] - это нормально

        return {
            "id": str(row[0]),
            "category_name": str(row[1]),
            "name": str(row[2]),
            "description": str(row[3]),
            "price": float(row[4]) if row[4] is not None else 0.0,
            "image_url": str(row[5]) if row[5] is not None else None,
            "unit": item_unit,
            "quantity": int(row[7]) if row[7] is not None else 0,
            "status": (
                str(row[8]) if row[8] is not None else app_config.ITEM_STATUS_AVAILABLE
            ),
            "order_steps": order_steps_list,
        }
    except (TypeError, ValueError, IndexError) as e:
        logger.error(
            f"Error parsing item data for item_id '{item_id_for_log}': {row} - {e}",
            exc_info=True,
        )
        return None


async def get_items_by_category(category_name: str) -> List[ItemData]:
    """Получает товары по имени категории."""
    if catalog_cache.is_initialized() and not catalog_cache.needs_update():
        cached_items = catalog_cache.get_items_by_category(category_name)
        if cached_items:  # Убедимся, что кэш не пустой для этой категории
            logger.debug(f"Using cached items for category '{category_name}'")
            return cached_items

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
    rows = await run_shillelagh_query(
        query, (category_name, app_config.ITEM_STATUS_UNAVAILABLE)
    )
    items = []
    for row_tuple in rows:
        item_data = _parse_item_row(
            row_tuple, str(row_tuple[0]) if row_tuple else "UNKNOWN_ID_IN_CATEGORY_LOOP"
        )
        if item_data:
            items.append(item_data)

    logger.info(f"Fetched {len(items)} items for category '{category_name}'.")
    return items


async def get_item(item_id: str) -> Optional[ItemData]:
    """Получает информацию о товаре по его ID."""
    if catalog_cache.is_initialized() and not catalog_cache.needs_update():
        cached_item = catalog_cache.get_item(item_id)
        if cached_item:
            logger.debug(f"Using cached item for ID '{item_id}'")
            return cached_item

    uri = _get_sheet_uri_with_gid(app_config.GSHEETS_ITEMS_URI)
    logger.debug(f"Fetching item by ID '{item_id}' from URI: {uri}")

    # Используем имя колонки ID из конфига в условии WHERE
    # Убедитесь, что Shillelagh правильно обрабатывает кавычки для имен колонок в WHERE
    # Если "{app_config.COL_ITEM_ID}" не работает, можно вернуться к 'A' (первая колонка)
    # или проверить документацию Shillelagh для правильного синтаксиса.
    # Для безопасности и совместимости, если ID всегда в первой колонке, 'A' может быть надежнее.
    # Но если COL_ITEM_ID настроен как "ID", то лучше использовать его.
    # В вашем коде было `WHERE A = ?`, оставим это, предполагая, что ID всегда в первой колонке.

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
        WHERE "{app_config.COL_ITEM_ID}" = ? 
    """
    # Примечание: изменил `WHERE A = ?` на `WHERE "{app_config.COL_ITEM_ID}" = ?` для большей консистентности.
    # Если это вызовет проблемы с Shillelagh, верните `WHERE A = ?`, если ID всегда в первой колонке.

    logger.debug(f"Executing query for item ID '{item_id}': {query}")

    row_tuple = await run_shillelagh_query(query, (item_id,), fetch_one=True)

    if row_tuple:
        item_data = _parse_item_row(row_tuple, item_id)
        if item_data:
            logger.info(
                f"Fetched item with id '{item_id}'. Unit: {item_data['unit']}, Order Steps: {item_data['order_steps']}"
            )
            return item_data

    logger.warning(f"Item with id '{item_id}' not found or failed to parse.")
    return None


async def sync_catalog_cache() -> None:
    """Синхронизирует кэш каталога с Google Sheets."""
    try:
        # Получаем текущие данные из Google Sheets
        current_categories = await get_all_categories()
        current_items = await get_all_items()

        # Группируем товары по категориям
        items_by_category = {}
        for item in current_items:
            category_name = item.get("category_name")
            if category_name:
                if category_name not in items_by_category:
                    items_by_category[category_name] = []
                items_by_category[category_name].append(item)

        if not catalog_cache.is_initialized():
            # Если кэш не инициализирован, инициализируем его
            catalog_cache.initialize(current_categories, items_by_category)
            return

        # Получаем текущие данные из кэша
        cached_categories = catalog_cache.get_categories()
        cached_items = {}
        for category in cached_categories:
            items = catalog_cache.get_items_by_category(category["name"])
            for item in items:
                cached_items[item["id"]] = item

        # Находим разницу в категориях
        current_category_ids = {cat["id"] for cat in current_categories}
        cached_category_ids = {cat["id"] for cat in cached_categories}
        updated_categories = [
            cat
            for cat in current_categories
            if cat["id"] not in cached_category_ids
            or cat != next((c for c in cached_categories if c["id"] == cat["id"]), None)
        ]

        # Находим разницу в товарах
        current_item_ids = {item["id"] for item in current_items}
        new_items = [item for item in current_items if item["id"] not in cached_items]
        removed_item_ids = cached_category_ids - current_item_ids

        if updated_categories or new_items or removed_item_ids:
            # Обновляем кэш частично
            catalog_cache.update_partial(
                new_items, removed_item_ids, updated_categories
            )
            logger.info(
                f"Catalog cache synchronized: updated {len(updated_categories)} categories, "
                f"added {len(new_items)} items, removed {len(removed_item_ids)} items"
            )
        else:
            logger.info("Catalog cache is up to date")

    except Exception as e:
        logger.error(f"Error synchronizing catalog cache: {e}", exc_info=True)
        raise


async def get_all_users() -> List[Dict[str, Any]]:
    """Получает список всех пользователей из Google Sheets."""
    uri = _get_sheet_uri_with_gid(app_config.GSHEETS_USERS_URI)
    query = f"""
        SELECT 
            "{app_config.COL_USER_TG_ID}",
            "{app_config.COL_USER_PRIVACY_ACCEPTED}"
        FROM "{uri}"
    """
    rows = await run_shillelagh_query(query)
    users = []
    for row in rows:
        if row and row[0] is not None:
            users.append(
                {
                    "user_id": int(row[0]),
                    "privacy_accepted": bool(row[1]) if row[1] is not None else False,
                }
            )
    return users


async def get_all_categories() -> List[Dict[str, Any]]:
    """Получает список всех категорий из Google Sheets."""
    uri = _get_sheet_uri_with_gid(app_config.GSHEETS_CATEGORIES_URI)
    query = f'SELECT DISTINCT "{app_config.COL_CATEGORY_NAME}" FROM "{uri}"'
    rows = await run_shillelagh_query(query)
    categories = []
    for row in rows:
        if row and row[0] is not None:
            category_name = str(row[0]).strip()
            if category_name:
                categories.append({"id": category_name, "name": category_name})
    return categories


async def get_all_items() -> List[Dict[str, Any]]:
    """Получает список всех товаров из Google Sheets."""
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
        WHERE "{app_config.COL_ITEM_STATUS}" != ?
    """
    rows = await run_shillelagh_query(query, (app_config.ITEM_STATUS_UNAVAILABLE,))
    items = []
    for row in rows:
        item_data = _parse_item_row(row, str(row[0]) if row else "UNKNOWN_ID")
        if item_data:
            items.append(item_data)
    return items


async def save_user_order_data(user_id: int, order_data: dict) -> None:
    """Сохраняет данные заказа пользователя."""
    try:
        # Получаем лист с данными пользователей
        worksheet = await get_worksheet(GSHEETS_USERS_URI)

        # Ищем пользователя
        cell = worksheet.find(str(user_id))
        if cell:
            row = cell.row
            # Обновляем данные заказа
            worksheet.update(f"order_data_{row}", json.dumps(order_data))
        else:
            # Если пользователь не найден, создаем новую запись
            worksheet.append_row(
                [
                    str(user_id),
                    False,  # privacy_accepted
                    json.dumps(order_data),  # order_data
                ]
            )
    except Exception as e:
        logger.error(f"Error saving user order data: {e}", exc_info=True)
        raise


async def get_user_order_data(user_id: int) -> dict:
    """Получает сохраненные данные заказа пользователя."""
    try:
        worksheet = await get_worksheet(GSHEETS_USERS_URI)
        cell = worksheet.find(str(user_id))
        if cell:
            row = cell.row
            order_data = worksheet.acell(f"order_data_{row}").value
            return json.loads(order_data) if order_data else {}
        return {}
    except Exception as e:
        logger.error(f"Error getting user order data: {e}", exc_info=True)
        return {}
