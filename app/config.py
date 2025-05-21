# app/config.py
from decouple import config, Csv, UndefinedValueError
import json

# Telegram Bot Token
TG_TOKEN = config('TG_TOKEN')

# Google Sheets Configuration
GSHEETS_ACCESS_TOKEN = config('GSHEETS_ACCESS_TOKEN', default=None)
GSHEETS_SERVICE_ACCOUNT_FILE = config('GSHEETS_SERVICE_ACCOUNT_FILE', default=None)
GSHEETS_SUBJECT_EMAIL = config('GSHEETS_SUBJECT_EMAIL', default=None)
GSHEETS_USE_APP_DEFAULT_CREDENTIALS = config('GSHEETS_USE_APP_DEFAULT_CREDENTIALS', default=False, cast=bool)

# --- Google Sheets URIs ---
try:
    GSHEETS_USERS_URI = config('GSHEETS_USERS_URI')
    # GSHEETS_CATEGORIES_URI = config('GSHEETS_CATEGORIES_URI') # УДАЛЯЕМ ЭТУ СТРОКУ
    GSHEETS_ITEMS_URI = config('GSHEETS_ITEMS_URI')
    GSHEETS_ORDERS_URI = config('GSHEETS_ORDERS_URI', default=None)
    GSHEETS_DELIVERY_SETTINGS_URI = config('GSHEETS_DELIVERY_SETTINGS_URI', default=None)
    GSHEETS_PAYMENT_SETTINGS_URI = config('GSHEETS_PAYMENT_SETTINGS_URI', default=None)
    GSHEETS_MAILINGS_URI = config('GSHEETS_MAILINGS_URI', default=None)

except UndefinedValueError as e:
    print(f"Критическая ошибка: одна из переменных GSHEETS_..._URI не определена в .env файле! {e}")

# --- Имена колонок для таблицы "Пользователи" (оставляем твои) ---
COL_USER_TG_ID = config('COL_USER_TG_ID', default='tg_id')
COL_USER_PRIVACY_ACCEPTED = config('COL_USER_PRIVACY_ACCEPTED', default='privacy_accepted')
COL_USER_ORDER_DATA_JSON = config('COL_USER_ORDER_DATA_JSON', default='order_data_json') # Для временного хранения данных заказа FSM

# --- Имена колонок для таблицы "Категории" (оставляем твое) ---
# COL_CATEGORY_NAME = config('COL_CATEGORY_NAME', default='name')

# --- Имена колонок для таблицы "Товары" (по ТЗ заказчика) ---
COL_ITEM_ID_Z = config('COL_ITEM_ID_Z', default='ID Товара') # Z - заказчик
COL_ITEM_NAME_Z = config('COL_ITEM_NAME_Z', default='Название Товара')
COL_ITEM_PHOTO_URL_Z = config('COL_ITEM_PHOTO_URL_Z', default='Ссылка на фото')
COL_ITEM_CATEGORY_Z = config('COL_ITEM_CATEGORY_Z', default='Категория')
COL_ITEM_DESCRIPTION_Z = config('COL_ITEM_DESCRIPTION_Z', default='Описание')
COL_ITEM_PRICE_PER_UNIT_Z = config('COL_ITEM_PRICE_PER_UNIT_Z', default='Цена за единицу')
COL_ITEM_MEASUREMENT_UNIT_Z = config('COL_ITEM_MEASUREMENT_UNIT_Z', default='Единица измерения') # "мл", "шт"
COL_ITEM_TYPE_Z = config('COL_ITEM_TYPE_Z', default='Тип товара') # "Объемный", "Штучный"
COL_ITEM_RASPIV_TYPE_Z = config('COL_ITEM_RASPIV_TYPE_Z', default='Тип распива') # "Обычный", "Совместный"
COL_ITEM_ORDER_STEP_Z = config('COL_ITEM_ORDER_STEP_Z', default='Шаг заказа') # Для "мл" это строка "1,2,5,10", для "шт" это "1"
COL_ITEM_AVAILABLE_QUANTITY_Z = config('COL_ITEM_AVAILABLE_QUANTITY_Z', default='Доступное количество')
COL_ITEM_STATUS_Z = config('COL_ITEM_STATUS_Z', default='Статус') # "Доступен", "Забронирован", "Недоступен"

# --- Имена колонок для таблицы "Заказы" (НОВЫЕ, по ТЗ заказчика) ---
COL_ORDER_NUMBER_Z = config('COL_ORDER_NUMBER_Z', default='Номер заказа')
COL_ORDER_USER_ID_Z = config('COL_ORDER_USER_ID_Z', default='ID пользователя') # tg_id
COL_ORDER_DATE_Z = config('COL_ORDER_DATE_Z', default='дата')
COL_ORDER_ITEMS_LIST_Z = config('COL_ORDER_ITEMS_LIST_Z', default='Список товаров(ID:Тип:Количество)') # "ID:Тип:Количество"
COL_ORDER_TOTAL_AMOUNT_Z = config('COL_ORDER_TOTAL_AMOUNT_Z', default='Общая сумма')
COL_ORDER_STATUS_Z = config('COL_ORDER_STATUS_Z', default='Статус') # "Принят", "Ожидает оплаты" и т.д.

# --- Имена колонок для таблицы "Тип доставки" (по ТЗ заказчика) ---
COL_DELIVERY_TYPE_Z = config('COL_DELIVERY_TYPE_Z', default='Тип доставки')
COL_DELIVERY_COST_Z = config('COL_DELIVERY_COST_Z', default='Стоимость')
COL_DELIVERY_ACTIVE_Z = config('COL_DELIVERY_ACTIVE_Z', default='Активность')
# COL_DELIVERY_DESCRIPTION_Z - если будешь использовать, добавь по аналогии

# --- Имена колонок для таблицы "Настройки платежей" (НОВЫЕ, по ТЗ заказчика) ---
COL_PAYMENT_FORMAT_Z = config('COL_PAYMENT_FORMAT_Z', default='Формат оплаты') # "СБП", "Tinkoff"
COL_PAYMENT_RECIPIENT_NAME_Z = config('COL_PAYMENT_RECIPIENT_NAME_Z', default='Наименование получателя')
COL_PAYMENT_ACCOUNT_NUMBER_Z = config('COL_PAYMENT_ACCOUNT_NUMBER_Z', default='Номер счета')
COL_PAYMENT_BANK_NAME_Z = config('COL_PAYMENT_BANK_NAME_Z', default='Банк')
COL_PAYMENT_BIK_Z = config('COL_PAYMENT_BIK_Z', default='БИК')
COL_PAYMENT_INN_Z = config('COL_PAYMENT_INN_Z', default='ИНН')
COL_PAYMENT_TERMINAL_KEY_Z = config('COL_PAYMENT_TERMINAL_KEY_Z', default='TerminalKey')
COL_PAYMENT_PASSWORD_Z = config('COL_PAYMENT_PASSWORD_Z', default='Password')

# --- Имена колонок для таблицы "Рассылки" (НОВЫЕ, по ТЗ заказчика) ---
COL_MAILING_ID_Z = config('COL_MAILING_ID_Z', default='ID рассылки')
COL_MAILING_TEXT_Z = config('COL_MAILING_TEXT_Z', default='Текст сообщения')
COL_MAILING_SEND_TIME_Z = config('COL_MAILING_SEND_TIME_Z', default='Время отправки (дата/время)')
COL_MAILING_SENT_STATUS_Z = config('COL_MAILING_SENT_STATUS_Z', default='Отправлено') # TRUE/FALSE


# --- Статусы товаров (используем твои, но они должны соответствовать значениям в колонке COL_ITEM_STATUS_Z) ---
ITEM_STATUS_RESERVED = "Забронирован"
ITEM_STATUS_AVAILABLE = "Доступен"  # Убедись, что это значение используется в таблице
ITEM_STATUS_UNAVAILABLE = "Недоступен"

# --- Единицы измерения (используем твои, должны соответствовать значениям в COL_ITEM_MEASUREMENT_UNIT_Z) ---
ITEM_UNIT_PCS = "шт"  # Убедись, что это значение используется в таблице
ITEM_UNIT_ML = "мл"   # Убедись, что это значение используется в таблице

# --- Остальные настройки ---
PRIVACY_URL = config('PRIVACY_URL',)
SUPPORT_URL = config('SUPPORT_URL',)
WELCOME_MESSAGE = """...""" # Твое сообщение
ABOUT = """...""" # Твое сообщение
ADMIN_IDS = config('ADMIN_IDS', default="936853523") # Пример чтения из .env