# app/config.py
from decouple import config, Csv, UndefinedValueError
import json # Для GSHEETS_SERVICE_ACCOUNT_INFO, если понадобится

# Telegram Bot Token
TG_TOKEN = config('TG_TOKEN')

# Google Sheets Configuration
GSHEETS_ACCESS_TOKEN = config('GSHEETS_ACCESS_TOKEN', default=None)
GSHEETS_SERVICE_ACCOUNT_FILE = config('GSHEETS_SERVICE_ACCOUNT_FILE', default=None)

# Для GSHEETS_SERVICE_ACCOUNT_INFO, если решишь передавать JSON напрямую
# GSHEETS_SERVICE_ACCOUNT_INFO_STR = config('GSHEETS_SERVICE_ACCOUNT_INFO', default=None)
# GSHEETS_SERVICE_ACCOUNT_INFO = json.loads(GSHEETS_SERVICE_ACCOUNT_INFO_STR) if GSHEETS_SERVICE_ACCOUNT_INFO_STR else None

GSHEETS_SUBJECT_EMAIL = config('GSHEETS_SUBJECT_EMAIL', default=None)
GSHEETS_USE_APP_DEFAULT_CREDENTIALS = config('GSHEETS_USE_APP_DEFAULT_CREDENTIALS', default=False, cast=bool)

# Google Sheets URIs
try:
    GSHEETS_USERS_URI = config('GSHEETS_USERS_URI')
    GSHEETS_CATEGORIES_URI = config('GSHEETS_CATEGORIES_URI')
    GSHEETS_ITEMS_URI = config('GSHEETS_ITEMS_URI')
except UndefinedValueError as e:
    print(f"Критическая ошибка: одна из переменных GSHEETS_..._URI не определена в .env файле! {e}")


# Имена колонок
COL_USER_TG_ID = config('COL_USER_TG_ID', default='tg_id')
COL_USER_PRIVACY_ACCEPTED = config('COL_USER_PRIVACY_ACCEPTED', default='privacy_accepted')
COL_CATEGORY_NAME = config('COL_CATEGORY_NAME', default='name') # ID и имя категории
COL_ITEM_ID = "ID"
COL_ITEM_CATEGORY_NAME = "Категория"
COL_ITEM_NAME = "Название"
COL_ITEM_DESCRIPTION = "Описание"
COL_ITEM_PRICE = "Цена"
COL_ITEM_IMAGE_URL = "URL изображения"
COL_ITEM_UNIT = "Единица измерения"  # Мл или Шт
COL_ITEM_QUANTITY = "Количество"  # Доступное количество
COL_ITEM_STATUS = "Статус"  # Забронирован, Доступен, Недоступен
COL_ITEM_ORDER_STEPS = "Шаг заказа"  # Шаги для заказа (для Мл)

# Статусы товаров
ITEM_STATUS_RESERVED = "Забронирован"
ITEM_STATUS_AVAILABLE = "Доступен"
ITEM_STATUS_UNAVAILABLE = "Недоступен"

# Единицы измерения
ITEM_UNIT_PCS = "Шт"
ITEM_UNIT_ML = "Мл"

PRIVACY_URL = config('PRIVACY_URL',)
SUPPORT_URL = config('SUPPORT_URL',)

# Приветственное сообщение
WELCOME_MESSAGE = """
Онлайн каталог магазина ⚫️TRUEPARFUME⚫️
Все ароматы строго оригинальные, здесь Вы можете ознакомиться с ароматекой и оформить заказ самостоятельно. 
Мы гарантируем:
- оригинальную парфюмерию❗️(исключены копии (подделки, реплики, аналоги и т. д.) Вы действительно можете нам доверять!
- доставку по всей России
- приятную цену на каждый аромат
- предельную честность
✍🏻 Для заказа жми
"""
ABOUT = """
Привет! TRUEPARFUME bot онлайн магазин, в котором можно заказать любую позицию из каталога онлайн с доставкой в любую точку мира, либо забрать самостоятельно :)
"""

# Список ID администраторов
ADMIN_IDS = [
    936853523,  # Замените на реальный ID администратора
]