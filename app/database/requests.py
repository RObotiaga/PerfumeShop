# app/database/requests.py
import asyncio
from typing import List, Optional, Dict, Any, Set, Tuple
from shillelagh.backends.apsw.db import connect as shillelagh_connect
import logging
from datetime import datetime
import time

# from google.oauth2.service_account import Credentials # Не используется напрямую здесь
# from googleapiclient.discovery import build # Не используется напрямую здесь
# from googleapiclient.errors import HttpError # Не используется напрямую здесь
import json

from app import config as app_config
from app.database.gsheets_setup import (
    get_sheet_gid,
    _extract_spreadsheet_id_from_uri,
    _extract_sheet_name_from_uri,
)  # Добавил для get_worksheet_gspread
from app.database.cache import privacy_cache, catalog_cache, cart_cache

# Импорт gspread для функций save/get_user_order_data, если они остаются с gspread
import gspread
from google.oauth2.service_account import (
    Credentials as ServiceAccountCredentials,
)  # Переименовал, чтобы не конфликтовать


logger = logging.getLogger(__name__)


# --- Gspread Client for specific direct operations (like order data) ---
# Эта функция может быть вынесена в gsheets_setup.py и импортирована оттуда
def get_gspread_client_for_direct_ops() -> Optional[gspread.Client]:
    if not app_config.GSHEETS_SERVICE_ACCOUNT_FILE:
        logger.error(
            "Файл сервисного аккаунта GSHEETS_SERVICE_ACCOUNT_FILE не указан для прямого доступа gspread."
        )
        return None
    try:
        scopes = [
            "https://www.googleapis.com/auth/spreadsheets"
        ]  # Для чтения/записи ячеек достаточно этого
        creds = ServiceAccountCredentials.from_service_account_file(
            app_config.GSHEETS_SERVICE_ACCOUNT_FILE, scopes=scopes
        )
        client = gspread.authorize(creds)
        return client
    except Exception as e:
        logger.error(
            f"Ошибка инициализации gspread клиента для прямых операций: {e}",
            exc_info=True,
        )
        return None


async def get_worksheet_gspread(uri: str) -> Optional[gspread.Worksheet]:
    # Используем run_in_executor, так как gspread - синхронная библиотека
    loop = asyncio.get_running_loop()

    def _get_worksheet_sync():
        gs_client = get_gspread_client_for_direct_ops()
        if not gs_client:
            return None
        try:
            spreadsheet_id = _extract_spreadsheet_id_from_uri(uri)
            sheet_name = _extract_sheet_name_from_uri(uri)
            spreadsheet = gs_client.open_by_key(spreadsheet_id)
            return spreadsheet.worksheet(sheet_name)
        except Exception as e_gs:
            logger.error(
                f"Ошибка при получении листа gspread для URI {uri} (sync): {e_gs}",
                exc_info=True,
            )
            return None

    return await loop.run_in_executor(None, _get_worksheet_sync)


# --- End Gspread Client ---


def _get_sheet_uri_with_gid(uri: str) -> str:
    base_uri = uri.split("/edit")[0]
    gid = get_sheet_gid(uri)
    if gid is None:
        logger.warning(
            f"GID не найден для URI {uri}, используем оригинальный URI без /edit"
        )
        sheet_name_part = uri.split("#sheet=")[1] if "#sheet=" in uri else None
        if sheet_name_part:
            return f"{base_uri}#sheet={sheet_name_part}"  # Для Shillelagh если имени листа достаточно
        return base_uri
    return f"{base_uri}#gid={gid}"


def get_gsheets_connection():
    adapter_kwargs = {"gsheetsapi": {}}
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
        logger.warning("GSHEETS: No specific auth configured.")

    try:
        connection = shillelagh_connect(":memory:", adapter_kwargs=adapter_kwargs)
        return connection
    except Exception as e:
        logger.error(f"Failed to connect to Shillelagh: {e}", exc_info=True)
        raise


async def run_shillelagh_query(
    query: str, params: tuple = (), fetch_one: bool = False, commit: bool = False
):
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
                f"Shillelagh query error: {e}. Query: {query}, Params: {params}",
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
    uri = _get_sheet_uri_with_gid(app_config.GSHEETS_USERS_URI)
    check_query = f'SELECT "{app_config.COL_USER_TG_ID}" FROM "{uri}" WHERE "{app_config.COL_USER_TG_ID}" = ?'
    user_exists = await run_shillelagh_query(check_query, (tg_id,), fetch_one=True)
    if not user_exists:
        insert_query = f'INSERT INTO "{uri}" ("{app_config.COL_USER_TG_ID}", "{app_config.COL_USER_PRIVACY_ACCEPTED}") VALUES (?, ?)'
        await run_shillelagh_query(insert_query, (tg_id, False), commit=True)
        logger.info(f"User {tg_id} added to Google Sheet.")
    # else:
    # logger.info(f"User {tg_id} already exists in Google Sheet.") # Можно убрать для чистоты логов


async def get_user_privacy_status(tg_id: int) -> bool:
    if privacy_cache.is_initialized() and not privacy_cache.needs_update():
        logger.debug(f"Privacy status for {tg_id} from cache")
        return privacy_cache.is_accepted(tg_id)

    logger.debug(
        f"Privacy status for {tg_id} from GSheets (cache miss or needs update)"
    )
    uri = _get_sheet_uri_with_gid(app_config.GSHEETS_USERS_URI)
    query = f'SELECT "{app_config.COL_USER_PRIVACY_ACCEPTED}" FROM "{uri}" WHERE "{app_config.COL_USER_TG_ID}" = ?'
    result = await run_shillelagh_query(query, (tg_id,), fetch_one=True)
    is_accepted = bool(result[0]) if result and result[0] is not None else False
    return is_accepted


async def accept_privacy_policy(tg_id: int) -> None:
    uri = _get_sheet_uri_with_gid(app_config.GSHEETS_USERS_URI)
    query = f'UPDATE "{uri}" SET "{app_config.COL_USER_PRIVACY_ACCEPTED}" = ? WHERE "{app_config.COL_USER_TG_ID}" = ?'
    await run_shillelagh_query(query, (True, tg_id), commit=True)
    privacy_cache.add_user(tg_id)  # Обновляем кэш немедленно
    logger.info(f"User {tg_id} accepted privacy policy.")


async def sync_privacy_cache() -> None:
    try:
        current_data = await get_all_users()
        current_accepted_users = {
            user["user_id"] for user in current_data if user.get("privacy_accepted")
        }

        if not privacy_cache.is_initialized():
            privacy_cache.initialize(current_accepted_users)
            logger.info("Privacy cache initialized with current users")
            return

        cached_users = privacy_cache.get_all_accepted_users()
        new_users = current_accepted_users - cached_users
        removed_users = cached_users - current_accepted_users

        if new_users or removed_users:
            privacy_cache.update_partial(new_users, removed_users)
            logger.info(
                f"Privacy cache synchronized: added {len(new_users)}, removed {len(removed_users)}"
            )
        else:
            logger.debug("Privacy cache is up to date during sync.")

        privacy_cache._last_update = time.time()
    except Exception as e:
        logger.error(f"Error synchronizing privacy cache: {e}", exc_info=True)


# --- CATEGORY OPERATIONS ---
CategoryData = Dict[str, Any]


async def get_categories() -> List[CategoryData]:
    if catalog_cache.is_initialized() and not catalog_cache.needs_update():
        cached_categories = catalog_cache.get_categories()
        if cached_categories:
            logger.debug("Using cached categories")
            return cached_categories
        else:
            logger.debug(
                "Cache is up-to-date, but no categories found in cache. Returning empty list."
            )
            return []

    logger.debug(
        "Fetching categories from GSheets (cache miss, needs update, or cache was empty)"
    )
    categories = await get_all_categories_from_gsheets()
    # Обновляем кеш после получения данных
    if categories:
        await sync_catalog_cache()
    return categories


async def get_all_categories_from_gsheets() -> List[Dict[str, Any]]:
    """Получает список всех уникальных категорий напрямую из листа 'Товары' для синхронизации кэша."""
    if not app_config.GSHEETS_ITEMS_URI or not app_config.COL_ITEM_CATEGORY_Z:
        logger.error(
            "GSHEETS_ITEMS_URI или COL_ITEM_CATEGORY_Z (для get_all_categories) не настроены."
        )
        return []

    uri = _get_sheet_uri_with_gid(app_config.GSHEETS_ITEMS_URI)
    category_col_in_items = app_config.COL_ITEM_CATEGORY_Z

    query = f'SELECT DISTINCT "{category_col_in_items}" FROM "{uri}" WHERE "{category_col_in_items}" IS NOT NULL AND TRIM("{category_col_in_items}") != ""'
    rows = await run_shillelagh_query(query)
    categories = []
    for row in rows:
        if row and row[0] is not None:
            category_name = str(row[0]).strip()
            if category_name:
                categories.append({"id": category_name, "name": category_name})
    categories = sorted(categories, key=lambda x: x["name"])
    return categories


async def sync_catalog_cache() -> None:
    try:
        current_categories = await get_all_categories_from_gsheets()
        current_items = await get_all_items_from_gsheets()

        # Группируем товары по категориям
        items_by_category = {}
        for item in current_items:
            category_name = item.get("category_name")
            if category_name:
                if category_name not in items_by_category:
                    items_by_category[category_name] = []
                items_by_category[category_name].append(item)

        if not catalog_cache.is_initialized():
            catalog_cache.initialize(current_categories, items_by_category)
            logger.info("Catalog cache initialized with categories derived from items")
        else:
            catalog_cache.update(current_categories, items_by_category)
            logger.info(
                "Catalog cache updated with categories derived from items (full refresh)"
            )

        catalog_cache._last_update = time.time()
    except Exception as e:
        logger.error(f"Error synchronizing catalog cache: {e}", exc_info=True)


# --- ITEM OPERATIONS ---
ItemData = Dict[str, Any]


def _parse_item_row(row: tuple, item_id_for_log: str) -> Optional[ItemData]:
    try:
        # Индексы колонок согласно ТЗ и примеру:
        # 0: ID Товара, 1: Название Товара, 2: Ссылка на фото, 3: Категория, 4: Описание,
        # 5: Цена за единицу, 6: Единица измерения, 7: Тип товара, 8: Тип распива,
        # 9: Шаг заказа, 10: Доступное количество, 11: Статус

        # Статус (берем из последней колонки, как и раньше)
        status_val = (
            str(row[11]).strip()
            if row[11] is not None
            else app_config.ITEM_STATUS_AVAILABLE
        )
        # Проверка на известные статусы, можно добавить больше логирования если статус неизвестен
        if status_val not in [
            app_config.ITEM_STATUS_AVAILABLE,
            app_config.ITEM_STATUS_RESERVED,
            app_config.ITEM_STATUS_UNAVAILABLE,
        ]:
            logger.warning(
                f"Unknown status '{status_val}' for item {item_id_for_log}. Defaulting to UNAVAILABLE."
            )
            status_val = app_config.ITEM_STATUS_UNAVAILABLE

        raw_unit_val = (
            str(row[6]).strip().lower() if row[6] is not None else ""
        )  # Единица измерения
        item_unit = app_config.ITEM_UNIT_PCS  # По умолчанию
        if raw_unit_val == app_config.ITEM_UNIT_ML.lower():
            item_unit = app_config.ITEM_UNIT_ML
        elif raw_unit_val == app_config.ITEM_UNIT_PCS.lower():
            item_unit = app_config.ITEM_UNIT_PCS
        elif raw_unit_val:  # Если что-то есть, но не распознано
            logger.warning(
                f"Unrecognized measurement unit '{raw_unit_val}' for item {item_id_for_log}. Defaulting to PCS."
            )

        order_steps_list = []
        raw_order_steps_str = str(row[9]).strip() if row[9] is not None else ""

        if item_unit == app_config.ITEM_UNIT_ML:
            if raw_order_steps_str:
                steps_str_no_space = raw_order_steps_str.replace(" ", "")
                parsed_step_strings = [
                    s.strip() for s in steps_str_no_space.split(",") if s.strip()
                ]
                for step_val_str in parsed_step_strings:
                    try:
                        step_float = float(step_val_str.replace(",", "."))
                        if step_float > 0:  # Шаги должны быть положительными
                            order_steps_list.append(step_float)
                    except ValueError:
                        logger.warning(
                            f"Invalid numeric value for ML order step '{step_val_str}' for item {item_id_for_log}."
                        )
                if order_steps_list:
                    order_steps_list = sorted(
                        list(set(order_steps_list))
                    )  # Уникальные, отсортированные, не пустые
                else:  # Если после парсинга шагов не осталось, а строка была
                    logger.warning(
                        f"No valid ML order steps parsed from '{raw_order_steps_str}' for item {item_id_for_log}."
                    )
            # Если строка шагов пуста для МЛ, order_steps_list останется пустым.
            # В клавиатуре get_item_cart_keyboard есть шаги по умолчанию для МЛ, если item_data['order_steps'] пуст.

        elif item_unit == app_config.ITEM_UNIT_PCS:
            if raw_order_steps_str:  # Если для ШТ что-то указано в "Шаг заказа"
                try:
                    # Штуки обычно целые, но для гибкости парсим как float и потом в int
                    step_val = float(raw_order_steps_str.replace(",", "."))
                    if step_val.is_integer() and step_val > 0:
                        order_steps_list = [int(step_val)]  # Обычно это будет [1]
                    else:
                        logger.warning(
                            f"Invalid PCS order step '{raw_order_steps_str}' for item {item_id_for_log} (must be positive integer). Defaulting to [1]."
                        )
                        order_steps_list = [1]
                except ValueError:
                    logger.warning(
                        f"Cannot parse PCS order step '{raw_order_steps_str}' for item {item_id_for_log}. Defaulting to [1]."
                    )
                    order_steps_list = [1]
            else:  # Если для ШТ шаг не указан, по умолчанию 1
                order_steps_list = [1]

        return {
            "id": str(row[0]).strip(),
            "name": str(row[1]).strip(),
            "image_url": (
                str(row[2]).strip() if row[2] and str(row[2]).strip() else None
            ),
            "category_name": str(row[3]).strip(),
            "description": str(row[4]).strip(),
            "price": (
                float(str(row[5]).replace(",", "."))
                if row[5] is not None and str(row[5]).strip()
                else 0.0
            ),
            "unit": item_unit,
            "item_type_z": str(row[7]).strip() if row[7] else None,
            "raspil_type_z": str(row[8]).strip() if row[8] else None,
            "order_steps": order_steps_list,
            "quantity": (
                int(float(str(row[10]).replace(",", ".")))
                if row[10] is not None and str(row[10]).strip()
                else 0
            ),
            "status": status_val,
        }
    except (
        Exception
    ) as e:  # Более общий Exception для непредвиденных ошибок на уровне строки
        logger.error(
            f"Critical error parsing item row for item_id '{item_id_for_log}': Data: {row} - Error: {e}",
            exc_info=True,
        )
        return None


async def get_items_by_category(category_name: str) -> List[ItemData]:
    if catalog_cache.is_initialized() and not catalog_cache.needs_update():
        cached_items = catalog_cache.get_items_by_category(category_name)
        logger.debug(
            f"Using cached items for category '{category_name}'. Count: {len(cached_items)}"
        )
        return cached_items

    logger.debug(
        f"Fetching items for category '{category_name}' from GSheets (cache miss or needs update)"
    )
    uri = _get_sheet_uri_with_gid(app_config.GSHEETS_ITEMS_URI)
    query = f'SELECT * FROM "{uri}" WHERE "{app_config.COL_ITEM_CATEGORY_Z}" = ?'
    rows = await run_shillelagh_query(query, (category_name,))
    items = [
        item for row in rows if (item := _parse_item_row(row, str(row[0]))) is not None
    ]
    # Обновляем кеш после получения данных
    if items:
        await sync_catalog_cache()
    return items


async def get_item(item_id: str) -> Optional[ItemData]:
    if catalog_cache.is_initialized() and not catalog_cache.needs_update():
        cached_item = catalog_cache.get_item(item_id)
        if cached_item:
            logger.debug(f"Using cached item for ID '{item_id}'")
            return cached_item
        logger.debug(f"Item ID '{item_id}' not found in up-to-date cache")
        return None

    logger.debug(
        f"Fetching item ID '{item_id}' from GSheets (cache miss, needs update, or not found in cache)"
    )
    uri = _get_sheet_uri_with_gid(app_config.GSHEETS_ITEMS_URI)
    query = f'SELECT * FROM "{uri}" WHERE "{app_config.COL_ITEM_ID}" = ?'
    row = await run_shillelagh_query(query, (item_id,), fetch_one=True)
    return _parse_item_row(row, item_id) if row else None


async def search_items_by_name(search_term: str) -> List[ItemData]:
    if not search_term or len(search_term) < 3:
        return []

    uri = _get_sheet_uri_with_gid(app_config.GSHEETS_ITEMS_URI)
    query = f"""
        SELECT
            "{app_config.COL_ITEM_ID_Z}", "{app_config.COL_ITEM_NAME_Z}", "{app_config.COL_ITEM_PHOTO_URL_Z}",
            "{app_config.COL_ITEM_CATEGORY_Z}", "{app_config.COL_ITEM_DESCRIPTION_Z}", "{app_config.COL_ITEM_PRICE_PER_UNIT_Z}",
            "{app_config.COL_ITEM_MEASUREMENT_UNIT_Z}", "{app_config.COL_ITEM_TYPE_Z}", "{app_config.COL_ITEM_RASPIV_TYPE_Z}",
            "{app_config.COL_ITEM_ORDER_STEP_Z}", "{app_config.COL_ITEM_AVAILABLE_QUANTITY_Z}", "{app_config.COL_ITEM_STATUS_Z}"
        FROM "{uri}"
        WHERE LOWER("{app_config.COL_ITEM_NAME_Z}") LIKE ? 
        AND "{app_config.COL_ITEM_STATUS_Z}" != ?
    """
    search_param = f"%{search_term.lower()}%"

    logger.debug(
        f"Executing search query: {query} with params: ('{search_param}', '{app_config.ITEM_STATUS_UNAVAILABLE}')"
    )

    try:
        rows = await run_shillelagh_query(
            query, (search_param, app_config.ITEM_STATUS_UNAVAILABLE)
        )
        items = []
        for row_tuple in rows:
            item_data = _parse_item_row(
                row_tuple,
                (
                    str(row_tuple[0])
                    if row_tuple and row_tuple[0]
                    else "UNKNOWN_ID_SEARCH_LOOP"
                ),
            )
            if item_data:
                items.append(item_data)
        logger.info(
            f"Found {len(items)} items in GSheets for search term '{search_term}'."
        )
        return items
    except Exception as e:
        logger.error(
            f"Error searching items by name '{search_term}' in GSheets: {e}",
            exc_info=True,
        )
        return []


async def get_all_items_from_gsheets() -> List[Dict[str, Any]]:
    if not app_config.GSHEETS_ITEMS_URI:
        return []
    uri = _get_sheet_uri_with_gid(app_config.GSHEETS_ITEMS_URI)
    query = f"""
        SELECT
            "{app_config.COL_ITEM_ID_Z}", "{app_config.COL_ITEM_NAME_Z}", "{app_config.COL_ITEM_PHOTO_URL_Z}",
            "{app_config.COL_ITEM_CATEGORY_Z}", "{app_config.COL_ITEM_DESCRIPTION_Z}", "{app_config.COL_ITEM_PRICE_PER_UNIT_Z}",
            "{app_config.COL_ITEM_MEASUREMENT_UNIT_Z}", "{app_config.COL_ITEM_TYPE_Z}", "{app_config.COL_ITEM_RASPIV_TYPE_Z}",
            "{app_config.COL_ITEM_ORDER_STEP_Z}", "{app_config.COL_ITEM_AVAILABLE_QUANTITY_Z}", "{app_config.COL_ITEM_STATUS_Z}"
        FROM "{uri}"
        WHERE "{app_config.COL_ITEM_STATUS_Z}" != ? 
    """
    rows = await run_shillelagh_query(query, (app_config.ITEM_STATUS_UNAVAILABLE,))
    items = []
    for row_tuple in rows:
        item_data = _parse_item_row(
            row_tuple,
            str(row_tuple[0]) if row_tuple and row_tuple[0] else "UNKNOWN_ID_ALL_ITEMS",
        )
        if item_data:
            items.append(item_data)
    return items


# --- User Order Data (using gspread directly as example, needs COL_USER_ORDER_DATA_JSON in config) ---
async def save_user_order_data(user_id: int, order_data: dict) -> None:
    if not hasattr(app_config, "COL_USER_ORDER_DATA_JSON"):
        logger.error(
            "COL_USER_ORDER_DATA_JSON is not configured. Cannot save order data."
        )
        return

    worksheet = await get_worksheet_gspread(app_config.GSHEETS_USERS_URI)
    if not worksheet:
        logger.error(
            f"Не удалось получить лист пользователей для сохранения данных заказа {user_id}."
        )
        return
    try:

        async def _save_sync():
            headers = worksheet.row_values(
                1
            )  # Предполагаем, что заголовки всегда в первой строке
            if not headers:
                logger.error(
                    f"Заголовки не найдены на листе пользователей {app_config.GSHEETS_USERS_URI}"
                )
                return False
            try:
                tg_id_col_index = headers.index(app_config.COL_USER_TG_ID) + 1
                order_data_col_index = (
                    headers.index(app_config.COL_USER_ORDER_DATA_JSON) + 1
                )
            except ValueError:
                logger.error(
                    f"Необходимые колонки ({app_config.COL_USER_TG_ID} или {app_config.COL_USER_ORDER_DATA_JSON}) не найдены в заголовках: {headers}"
                )
                return False

            cell = worksheet.find(str(user_id), in_column=tg_id_col_index)
            if cell:
                worksheet.update_cell(
                    cell.row, order_data_col_index, json.dumps(order_data)
                )
                logger.info(
                    f"Данные заказа для пользователя {user_id} обновлены (gspread)."
                )
                return True
            else:  # Если пользователь не найден, создаем новую запись (это должно быть редкостью)
                new_row = [None] * len(headers)
                new_row[tg_id_col_index - 1] = str(user_id)
                new_row[headers.index(app_config.COL_USER_PRIVACY_ACCEPTED)] = (
                    await get_user_privacy_status(user_id)
                )  # Текущий статус
                new_row[order_data_col_index - 1] = json.dumps(order_data)
                worksheet.append_row(new_row)
                logger.info(
                    f"Пользователь {user_id} добавлен с данными заказа (gspread)."
                )
                return True

        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, _save_sync)
    except Exception as e:
        logger.error(
            f"Error saving user order data for {user_id} (gspread): {e}", exc_info=True
        )


async def get_user_order_data(user_id: int) -> dict:
    if not hasattr(app_config, "COL_USER_ORDER_DATA_JSON"):
        logger.error(
            "COL_USER_ORDER_DATA_JSON is not configured. Cannot get order data."
        )
        return {}

    worksheet = await get_worksheet_gspread(app_config.GSHEETS_USERS_URI)
    if not worksheet:
        logger.error(
            f"Не удалось получить лист пользователей для получения данных заказа {user_id}."
        )
        return {}
    try:

        def _get_sync():
            headers = worksheet.row_values(1)
            if not headers:
                return {}
            try:
                tg_id_col_index = headers.index(app_config.COL_USER_TG_ID) + 1
                order_data_col_index = (
                    headers.index(app_config.COL_USER_ORDER_DATA_JSON) + 1
                )
            except ValueError:
                return {}

            cell = worksheet.find(str(user_id), in_column=tg_id_col_index)
            if cell:
                order_data_json = worksheet.cell(cell.row, order_data_col_index).value
                return (
                    json.loads(order_data_json)
                    if order_data_json and order_data_json.strip()
                    else {}
                )
            return {}

        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, _get_sync)
    except Exception as e:
        logger.error(
            f"Error getting user order data for {user_id} (gspread): {e}", exc_info=True
        )
        return {}
