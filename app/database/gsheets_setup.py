# app/database/gsheets_setup.py
import gspread
from google.oauth2.service_account import Credentials
import logging
from typing import List, Dict, Tuple, Optional

from app import config as app_config  # Ваш модуль конфигурации

logger = logging.getLogger(__name__)

# Описание ожидаемой структуры: URI -> (имя листа, gid, [заголовки])
EXPECTED_SHEETS_STRUCTURE: Dict[str, Tuple[str, int, List[str]]] = {}
# Словарь для хранения gid листов: URI -> gid
SHEET_GIDS: Dict[str, int] = {}


def _initialize_expected_structure():
    """Инициализирует EXPECTED_SHEETS_STRUCTURE на основе конфигурации."""
    global EXPECTED_SHEETS_STRUCTURE
    EXPECTED_SHEETS_STRUCTURE = (
        {}
    )  # Очищаем на случай повторного вызова (хотя обычно не нужно)

    # Таблица Пользователи (остается)
    if app_config.GSHEETS_USERS_URI and app_config.COL_USER_TG_ID:  # Проверяем основные
        EXPECTED_SHEETS_STRUCTURE[app_config.GSHEETS_USERS_URI] = (
            _extract_sheet_name_from_uri(app_config.GSHEETS_USERS_URI),
            0,
            [
                app_config.COL_USER_TG_ID,
                app_config.COL_USER_PRIVACY_ACCEPTED,
                app_config.COL_USER_ORDER_DATA_JSON,
            ],
        )

    # Таблица Товары (обновляем колонки)
    if app_config.GSHEETS_ITEMS_URI and all(
        [
            app_config.COL_ITEM_ID_Z,
            app_config.COL_ITEM_NAME_Z,
            app_config.COL_ITEM_PHOTO_URL_Z,
            app_config.COL_ITEM_CATEGORY_Z,
            app_config.COL_ITEM_DESCRIPTION_Z,
            app_config.COL_ITEM_PRICE_PER_UNIT_Z,
            app_config.COL_ITEM_MEASUREMENT_UNIT_Z,
            app_config.COL_ITEM_TYPE_Z,
            app_config.COL_ITEM_RASPIV_TYPE_Z,
            app_config.COL_ITEM_ORDER_STEP_Z,
            app_config.COL_ITEM_AVAILABLE_QUANTITY_Z,
            app_config.COL_ITEM_STATUS_Z,
        ]
    ):
        EXPECTED_SHEETS_STRUCTURE[app_config.GSHEETS_ITEMS_URI] = (
            _extract_sheet_name_from_uri(app_config.GSHEETS_ITEMS_URI),
            0,
            [
                app_config.COL_ITEM_ID_Z,
                app_config.COL_ITEM_NAME_Z,
                app_config.COL_ITEM_PHOTO_URL_Z,
                app_config.COL_ITEM_CATEGORY_Z,
                app_config.COL_ITEM_DESCRIPTION_Z,
                app_config.COL_ITEM_PRICE_PER_UNIT_Z,
                app_config.COL_ITEM_MEASUREMENT_UNIT_Z,
                app_config.COL_ITEM_TYPE_Z,
                app_config.COL_ITEM_RASPIV_TYPE_Z,
                app_config.COL_ITEM_ORDER_STEP_Z,
                app_config.COL_ITEM_AVAILABLE_QUANTITY_Z,
                app_config.COL_ITEM_STATUS_Z,
            ],
        )

    # Таблица Заказы (НОВАЯ)
    if app_config.GSHEETS_ORDERS_URI and all(
        [
            app_config.COL_ORDER_NUMBER_Z,
            app_config.COL_ORDER_USER_ID_Z,
            app_config.COL_ORDER_DATE_Z,
            app_config.COL_ORDER_ITEMS_LIST_Z,
            app_config.COL_ORDER_TOTAL_AMOUNT_Z,
            app_config.COL_ORDER_STATUS_Z,
        ]
    ):
        EXPECTED_SHEETS_STRUCTURE[app_config.GSHEETS_ORDERS_URI] = (
            _extract_sheet_name_from_uri(app_config.GSHEETS_ORDERS_URI),
            0,
            [
                app_config.COL_ORDER_NUMBER_Z,
                app_config.COL_ORDER_USER_ID_Z,
                app_config.COL_ORDER_DATE_Z,
                app_config.COL_ORDER_ITEMS_LIST_Z,
                app_config.COL_ORDER_TOTAL_AMOUNT_Z,
                app_config.COL_ORDER_STATUS_Z,
            ],
        )

    # Таблица Тип доставки (обновляем колонки)
    if app_config.GSHEETS_DELIVERY_SETTINGS_URI and all(
        [
            app_config.COL_DELIVERY_TYPE_Z,
            app_config.COL_DELIVERY_COST_Z,
            app_config.COL_DELIVERY_ACTIVE_Z,
        ]
    ):
        description_col = (
            [app_config.COL_DELIVERY_DESCRIPTION_Z]
            if hasattr(app_config, "COL_DELIVERY_DESCRIPTION_Z")
            and app_config.COL_DELIVERY_DESCRIPTION_Z
            else []
        )
        EXPECTED_SHEETS_STRUCTURE[app_config.GSHEETS_DELIVERY_SETTINGS_URI] = (
            _extract_sheet_name_from_uri(app_config.GSHEETS_DELIVERY_SETTINGS_URI),
            0,
            [
                app_config.COL_DELIVERY_TYPE_Z,
                app_config.COL_DELIVERY_COST_Z,
                app_config.COL_DELIVERY_ACTIVE_Z,
            ]
            + description_col,
        )

    # Таблица Настройки платежей (НОВАЯ)
    if app_config.GSHEETS_PAYMENT_SETTINGS_URI and all(
        [
            app_config.COL_PAYMENT_FORMAT_Z,
            app_config.COL_PAYMENT_RECIPIENT_NAME_Z,
            app_config.COL_PAYMENT_ACCOUNT_NUMBER_Z,
            app_config.COL_PAYMENT_BANK_NAME_Z,
            app_config.COL_PAYMENT_BIK_Z,
            app_config.COL_PAYMENT_INN_Z,
            app_config.COL_PAYMENT_TERMINAL_KEY_Z,
            app_config.COL_PAYMENT_PASSWORD_Z,
        ]
    ):
        EXPECTED_SHEETS_STRUCTURE[app_config.GSHEETS_PAYMENT_SETTINGS_URI] = (
            _extract_sheet_name_from_uri(app_config.GSHEETS_PAYMENT_SETTINGS_URI),
            0,
            [
                app_config.COL_PAYMENT_FORMAT_Z,
                app_config.COL_PAYMENT_RECIPIENT_NAME_Z,
                app_config.COL_PAYMENT_ACCOUNT_NUMBER_Z,
                app_config.COL_PAYMENT_BANK_NAME_Z,
                app_config.COL_PAYMENT_BIK_Z,
                app_config.COL_PAYMENT_INN_Z,
                app_config.COL_PAYMENT_TERMINAL_KEY_Z,
                app_config.COL_PAYMENT_PASSWORD_Z,
            ],
        )

    # Таблица Рассылки (НОВАЯ)
    if app_config.GSHEETS_MAILINGS_URI and all(
        [
            app_config.COL_MAILING_ID_Z,
            app_config.COL_MAILING_TEXT_Z,
            app_config.COL_MAILING_SEND_TIME_Z,
            app_config.COL_MAILING_SENT_STATUS_Z,
        ]
    ):
        EXPECTED_SHEETS_STRUCTURE[app_config.GSHEETS_MAILINGS_URI] = (
            _extract_sheet_name_from_uri(app_config.GSHEETS_MAILINGS_URI),
            0,
            [
                app_config.COL_MAILING_ID_Z,
                app_config.COL_MAILING_TEXT_Z,
                app_config.COL_MAILING_SEND_TIME_Z,
                app_config.COL_MAILING_SENT_STATUS_Z,
            ],
        )

    if not EXPECTED_SHEETS_STRUCTURE:
        logger.warning(
            "Структура ожидаемых Google Sheets не была инициализирована. Проверьте конфигурацию URI и имен колонок."
        )


def _extract_sheet_name_from_uri(uri: str) -> str:
    """Извлекает имя листа из URI (например, ...#sheet=MySheetName)."""
    try:
        return uri.split("#sheet=")[1]
    except IndexError:
        logger.error(
            f"Не удалось извлечь имя листа из URI: {uri}. Убедитесь, что URI содержит '#sheet=ИмяЛиста'."
        )
        raise ValueError(f"Некорректный формат URI для имени листа: {uri}")


def _extract_spreadsheet_id_from_uri(uri: str) -> str:
    """Извлекает ID таблицы из URI (например, .../d/SPREADSHEET_ID/edit...)."""
    try:
        return uri.split("/d/")[1].split("/")[0]
    except IndexError:
        logger.error(f"Не удалось извлечь ID таблицы из URI: {uri}.")
        raise ValueError(f"Некорректный формат URI для ID таблицы: {uri}")


def get_gspread_client() -> Optional[gspread.Client]:
    """Инициализирует и возвращает клиент gspread."""
    if not app_config.GSHEETS_SERVICE_ACCOUNT_FILE:
        logger.error("Файл сервисного аккаунта GSHEETS_SERVICE_ACCOUNT_FILE не указан.")
        return None
    try:
        scopes = [
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive.file",  # Для создания листов и файлов
        ]
        creds = Credentials.from_service_account_file(
            app_config.GSHEETS_SERVICE_ACCOUNT_FILE, scopes=scopes
        )
        client = gspread.authorize(creds)
        return client
    except Exception as e:
        logger.error(f"Ошибка инициализации gspread клиента: {e}", exc_info=True)
        return None


async def ensure_google_sheets_setup():
    """
    Проверяет наличие Google Таблиц, листов и заголовков.
    Создает их, если они отсутствуют.
    """
    _initialize_expected_structure()  # Заполняем структуру при вызове
    if not EXPECTED_SHEETS_STRUCTURE:
        logger.error(
            "Не удалось определить структуру таблиц из конфигурации. Настройка прервана."
        )
        return

    logger.info("Запуск проверки и настройки структуры Google Sheets...")
    gs_client = get_gspread_client()
    if not gs_client:
        logger.error(
            "Не удалось получить gspread клиент. Настройка Google Sheets прервана."
        )
        return

    # Группируем листы по ID таблицы, чтобы открывать каждую таблицу только один раз
    spreadsheets_map: Dict[str, List[Tuple[str, List[str]]]] = {}
    for uri, (sheet_name, _, headers) in EXPECTED_SHEETS_STRUCTURE.items():
        try:
            spreadsheet_id = _extract_spreadsheet_id_from_uri(uri)
            if spreadsheet_id not in spreadsheets_map:
                spreadsheets_map[spreadsheet_id] = []
            spreadsheets_map[spreadsheet_id].append((sheet_name, headers))
        except ValueError:
            logger.warning(f"Пропуск настройки для некорректного URI: {uri}")
            continue

    for spreadsheet_id, sheet_configs in spreadsheets_map.items():
        try:
            spreadsheet = gs_client.open_by_key(spreadsheet_id)
            logger.info(
                f"Открыта таблица: '{spreadsheet.title}' (ID: {spreadsheet_id})"
            )

            # Получаем все листы и их gid
            worksheets = spreadsheet.worksheets()
            worksheet_map = {ws.title: ws for ws in worksheets}
            existing_worksheets_titles = list(worksheet_map.keys())

            for sheet_name, headers in sheet_configs:
                worksheet = None
                if sheet_name in existing_worksheets_titles:
                    logger.info(
                        f"Лист '{sheet_name}' уже существует в таблице '{spreadsheet.title}'."
                    )
                    worksheet = worksheet_map[sheet_name]
                    # Сохраняем gid листа
                    gid = worksheet.id
                    SHEET_GIDS[spreadsheet_id + "#" + sheet_name] = gid
                    logger.info(f"Сохранен gid {gid} для листа '{sheet_name}'")
                else:
                    logger.info(
                        f"Лист '{sheet_name}' не найден. Создание листа в таблице '{spreadsheet.title}'..."
                    )
                    try:
                        # Создаем лист с достаточным количеством строк и колонок (можно настроить)
                        worksheet = spreadsheet.add_worksheet(
                            title=sheet_name,
                            rows="100",
                            cols=str(max(20, len(headers))),
                        )
                        # Сохраняем gid нового листа
                        gid = worksheet.id
                        SHEET_GIDS[spreadsheet_id + "#" + sheet_name] = gid
                        logger.info(f"Лист '{sheet_name}' успешно создан с gid {gid}")
                    except Exception as e_add:
                        logger.error(
                            f"Не удалось создать лист '{sheet_name}': {e_add}",
                            exc_info=True,
                        )
                        continue  # Переходим к следующей конфигурации листа

                if worksheet:
                    # Проверяем заголовки
                    # worksheet.get('A1:Z1') вернет список списков, даже если строка пуста ([[]])
                    # worksheet.row_values(1) вернет список значений или None/пустой список, если строка пустая
                    current_headers = []
                    try:
                        current_headers = worksheet.row_values(
                            1
                        )  # Получаем значения первой строки
                    except gspread.exceptions.APIError as e_api:
                        # Может возникнуть, если лист абсолютно пуст и API не может определить размер
                        if "exceeds grid limits" in str(
                            e_api
                        ).lower() or "Unable to parse range" in str(e_api):
                            logger.info(
                                f"Лист '{sheet_name}' пуст или имеет неопределенные границы, заголовки будут записаны."
                            )
                            current_headers = []
                        else:
                            logger.error(
                                f"API ошибка при чтении заголовков с листа '{sheet_name}': {e_api}"
                            )
                            continue  # Пропустить этот лист

                    # Удаляем пустые строки или None в конце списка заголовков, которые может вернуть gspread
                    cleaned_current_headers = [
                        h
                        for h in current_headers
                        if h is not None and str(h).strip() != ""
                    ]

                    if cleaned_current_headers != headers:
                        logger.info(
                            f"Заголовки на листе '{sheet_name}' ({cleaned_current_headers}) "
                            f"не соответствуют ожидаемым ({headers}) или отсутствуют. Запись/Обновление заголовков..."
                        )
                        try:
                            # Обновляем первую строку с заголовками
                            worksheet.update(
                                "A1", [headers], value_input_option="USER_ENTERED"
                            )
                            logger.info(
                                f"Заголовки для листа '{sheet_name}' успешно записаны/обновлены."
                            )
                        except Exception as e_update:
                            logger.error(
                                f"Не удалось записать/обновить заголовки для листа '{sheet_name}': {e_update}",
                                exc_info=True,
                            )
                    else:
                        logger.info(f"Заголовки на листе '{sheet_name}' уже корректны.")

        except gspread.exceptions.SpreadsheetNotFound:
            logger.error(
                f"Таблица Google с ID '{spreadsheet_id}' не найдена. "
                f"Убедитесь, что ID корректен и у сервисного аккаунта есть доступ к этой таблице."
            )
        except Exception as e:
            logger.error(
                f"Ошибка при работе с таблицей ID '{spreadsheet_id}': {e}",
                exc_info=True,
            )

    logger.info("Проверка и настройка структуры Google Sheets завершена.")
    logger.info(f"Сохраненные gid листов: {SHEET_GIDS}")


def get_sheet_gid(uri: str) -> Optional[int]:
    """Возвращает gid листа по его URI."""
    spreadsheet_id = _extract_spreadsheet_id_from_uri(uri)
    sheet_name = _extract_sheet_name_from_uri(uri)
    key = f"{spreadsheet_id}#{sheet_name}"
    return SHEET_GIDS.get(key)
