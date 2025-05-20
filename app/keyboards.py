# app/keyboards.py
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
from app.database import requests as rq # Импортируем обновленные запросы
from app.database.cache import cart_cache
import logging

from app import config as app_config

logger = logging.getLogger(__name__)

# Клавиатура для согласия с политикой
privacy_keyboard = InlineKeyboardMarkup(
    inline_keyboard=[
        [InlineKeyboardButton(text="📜 Политика конфиденциальности", url=app_config.PRIVACY_URL)],
        [InlineKeyboardButton(text="✅ Согласиться", callback_data="privacy_accept")]
    ]
)

# Основное меню
menu = InlineKeyboardMarkup(inline_keyboard=[
    [InlineKeyboardButton(text='Каталог', callback_data='catalog')],
    [InlineKeyboardButton(text='🛒 Корзина', callback_data='cart')],
    [InlineKeyboardButton(text='👨‍💼 Связаться с поддержкой', url=app_config.SUPPORT_URL)],
    [InlineKeyboardButton(text='Информация о магазине', callback_data='about')],
])

async def categories_keyboard_builder(): # Переименовал для ясности, что это builder
    all_categories_data = await rq.get_categories() # Возвращает List[Dict[str, Any]]
    builder = InlineKeyboardBuilder()
    if all_categories_data:
        for category_data in all_categories_data:
            # category_data это словарь, например: {"id": "Ноутбуки", "name": "Ноутбуки"}
            # Используем category_data['id'] (которое равно имени категории) для callback_data
            builder.row(InlineKeyboardButton(text=category_data['name'], callback_data=f"category_{category_data['id']}"))
    builder.row(InlineKeyboardButton(text='На главную', callback_data='start'))
    return builder.as_markup()

async def get_items_by_category_kb(category_name: str): # Принимает имя категории
    all_items_data = await rq.get_items_by_category(category_name) # Возвращает List[Dict[str, Any]]
    builder = InlineKeyboardBuilder()
    if all_items_data:
        for item_data in all_items_data:
            # item_data это словарь, например: {"id": "NB001", "name": "Ультрабук", ...}
            builder.row(InlineKeyboardButton(text=item_data['name'], callback_data=f"item_{item_data['id']}"))
    builder.row(InlineKeyboardButton(text='К категориям', callback_data='catalog'))
    return builder.as_markup()

async def back_to_category_kb(category_name: str, page: int = 1): # Добавляем параметр page
    # Убедимся, что category_name не пустое, чтобы не создавать некорректный callback_data
    if not category_name:
        # Если имя категории по какой-то причине пустое, предложим вернуться в общий каталог
        return InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text='В каталог', callback_data='catalog')]
        ])
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text='Назад к категории', callback_data=f'category:{category_name}:page:{page}')]
    ])

def get_items_keyboard(items: list, category_name: str, page: int = 1, items_per_page: int = 10) -> InlineKeyboardMarkup:
    """
    Создает клавиатуру с товарами и пагинацией.
    
    Args:
        items: Список товаров
        category_name: Название категории
        page: Текущая страница (начиная с 1)
        items_per_page: Количество товаров на странице
    """
    builder = InlineKeyboardBuilder()
    
    # Вычисляем индексы для текущей страницы
    start_idx = (page - 1) * items_per_page
    end_idx = start_idx + items_per_page
    current_page_items = items[start_idx:end_idx]
    
    # Добавляем кнопки товаров в столбик
    for item in current_page_items:
        # Формируем текст кнопки с учетом статуса и единиц измерения
        status_emoji = "🔒" if item['status'] == app_config.ITEM_STATUS_RESERVED else "✅"
        quantity_text = f" ({item['quantity']} {item['unit']})" if item['quantity'] > 0 else ""
        button_text = f"{status_emoji} {item['name']} - {item['price']}₽{quantity_text}"
        
        builder.row(InlineKeyboardButton(
            text=button_text,
            callback_data=f"item:{item['id']}"
        ))
    
    # Вычисляем общее количество страниц
    total_pages = (len(items) + items_per_page - 1) // items_per_page
    
    # Добавляем кнопки пагинации
    pagination_row = []
    
    # Кнопка "Предыдущая страница"
    if page > 1:
        pagination_row.append(
            InlineKeyboardButton(
                text="◀️",
                callback_data=f"category:{category_name}:page:{page-1}"
            )
        )
    
    # Кнопка с номером текущей страницы
    if total_pages > 0 : # Отображаем только если есть страницы
        pagination_row.append(
            InlineKeyboardButton(
                text=f"{page}/{total_pages}",
                callback_data="ignore"  # Эта кнопка не должна ничего делать
            )
        )
    
    # Кнопка "Следующая страница"
    if page < total_pages:
        pagination_row.append(
            InlineKeyboardButton(
                text="▶️",
                callback_data=f"category:{category_name}:page:{page+1}"
            )
        )
    
    # Добавляем кнопки пагинации в отдельный ряд, если они есть
    if pagination_row:
        builder.row(*pagination_row)
    
    # Добавляем кнопку "Назад в каталог" в отдельный ряд
    builder.row(InlineKeyboardButton(
        text="◀️ Назад в каталог",
        callback_data="catalog"
    ))
    
    return builder.as_markup()

def get_catalog_keyboard(categories: list = None) -> InlineKeyboardMarkup:
    """Создает клавиатуру с категориями товаров."""
    builder = InlineKeyboardBuilder()
    
    if categories:
        # Добавляем кнопки категорий в столбик
        for category in categories:
            builder.row(InlineKeyboardButton(
                text=category['name'],
                callback_data=f"category:{category['name']}:page:1"
            ))

    # Добавляем кнопку "Назад в главное меню" в отдельный ряд
    builder.row(InlineKeyboardButton(
        text="◀️ Назад в главное меню",
        callback_data="start"
    ))
    
    return builder.as_markup()

def get_cart_keyboard() -> InlineKeyboardMarkup:
    """Создает клавиатуру для корзины."""
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(
        text="🛒 Корзина",
        callback_data="cart"
    ))
    return builder.as_markup()

def get_item_cart_keyboard(item_id: str, user_id: int, item_data: dict) -> InlineKeyboardMarkup:
    """Создает клавиатуру для управления товаром в корзине."""
    builder = InlineKeyboardBuilder()
    
    # Получаем текущее количество в корзине
    current_quantity = cart_cache.get_item_quantity(user_id, item_id)
    
    # Добавляем кнопки в зависимости от единиц измерения
    if item_data['unit'] == app_config.ITEM_UNIT_PCS:
        # Для товаров в штуках
        if current_quantity > 0:
            # Показываем кнопки уменьшения только если товар уже в корзине
            builder.row(
                InlineKeyboardButton(text="-10", callback_data=f"cart:decrease:{item_id}:10"),
                InlineKeyboardButton(text="-1", callback_data=f"cart:decrease:{item_id}:1"),
                InlineKeyboardButton(text=f"{current_quantity} шт", callback_data="ignore"),
                InlineKeyboardButton(text="+1", callback_data=f"cart:increase:{item_id}:1"),
                InlineKeyboardButton(text="+10", callback_data=f"cart:increase:{item_id}:10")
            )
        else:
            # Если товара нет в корзине, показываем только кнопки добавления
            builder.row(
                InlineKeyboardButton(text="0 шт", callback_data="ignore"),
                InlineKeyboardButton(text="+1", callback_data=f"cart:increase:{item_id}:1"),
                InlineKeyboardButton(text="+10", callback_data=f"cart:increase:{item_id}:10")
            )
    elif item_data['unit'] == app_config.ITEM_UNIT_ML: # Явно проверяем МЛ
        # Для товаров в миллилитрах
        if current_quantity > 0:
            # Показываем кнопку сброса только если товар в корзине
            builder.row(InlineKeyboardButton(text="Сбросить", callback_data=f"cart:reset:{item_id}"))
        
        # Добавляем кнопки с шагами заказа
        # item_data['order_steps'] будет списком (возможно, пустым) из requests.py
        specific_order_steps = item_data.get('order_steps')

        # Используем specific_order_steps, если они не пустые, иначе используем шаги по умолчанию
        if specific_order_steps and isinstance(specific_order_steps, list) and len(specific_order_steps) > 0:
            order_steps_to_use = specific_order_steps
            logger.debug(f"Using specific order steps for ML item {item_id}: {specific_order_steps}")
        else:
            order_steps_to_use = [1, 2, 3, 5, 10, 15, 20] # Шаги по умолчанию для Мл
            logger.info(f"For ML item {item_id}, specific order_steps were '{specific_order_steps}'. Using default steps: {order_steps_to_use}.")
        
        buttons = []
        for step in order_steps_to_use:
            # Отображаем целые числа без ".0"
            step_text = str(int(step)) if isinstance(step, float) and step.is_integer() else str(step)
            buttons.append(InlineKeyboardButton(
                text=f"+{step_text}",
                callback_data=f"cart:increase:{item_id}:{step}" # callback_data может содержать float
            ))
        
        if buttons: # Добавляем ряд, только если кнопки были созданы
            builder.row(*buttons)
        else:
            # Эта ситуация теперь маловероятна, так как есть order_steps_to_use по умолчанию
            logger.warning(f"No order step buttons generated for Мл item {item_id}. Steps evaluated: {order_steps_to_use}")

    else: # Если единица измерения не Шт и не Мл
        logger.warning(f"Unknown unit type '{item_data['unit']}' for item {item_id}. No cart management buttons generated.")


    # Добавляем кнопку корзины
    builder.row(InlineKeyboardButton(text="🛒 Корзина", callback_data="cart"))
    
    # Добавляем кнопку возврата в категорию
    category_name_for_back = item_data.get('category_name', '')
    if category_name_for_back: # Только если имя категории есть
        builder.row(InlineKeyboardButton(
            text="◀️ Назад к категории",
            callback_data=f"category:{category_name_for_back}:page:1" # По умолчанию на 1ю страницу
        ))
    else: # Если нет имени категории, кнопка "Назад в каталог"
        builder.row(InlineKeyboardButton(
            text="◀️ Назад в каталог",
            callback_data="catalog"
        ))

    return builder.as_markup()

def get_cart_items_keyboard(cart_items: list = None) -> InlineKeyboardMarkup:
    """Создает клавиатуру со списком товаров в корзине."""
    builder = InlineKeyboardBuilder()
    
    if cart_items:
        for item in cart_items:
            builder.row(InlineKeyboardButton(
                text=f"❌ {item['name']} - {item['quantity']} {item['unit']}",
                callback_data=f"cart:remove:{item['id']}"
            ))
        builder.row(
        InlineKeyboardButton(text="🗑 Очистить корзину", callback_data="cart:clear"),
        InlineKeyboardButton(text="Заказать", callback_data="order"),
        InlineKeyboardButton(text="◀️ Назад", callback_data="start")
    )
    # Добавляем кнопки управления корзиной
    builder.row(
        InlineKeyboardButton(text="◀️ Назад", callback_data="start")
    )
    
    return builder.as_markup()

def get_admin_keyboard() -> InlineKeyboardMarkup:
    """Создает клавиатуру для администратора."""
    builder = InlineKeyboardBuilder()
    
    builder.row(InlineKeyboardButton(
        text="📊 Статистика",
        callback_data="admin:stats"
    ))
    
    builder.row(InlineKeyboardButton(
        text="🔄 Синхронизация",
        callback_data="admin:sync"
    ))
    
    builder.row(InlineKeyboardButton(
        text="◀️ Назад",
        callback_data="start"
    ))
    
    return builder.as_markup()