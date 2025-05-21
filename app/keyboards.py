# app/keyboards.py
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
from app.database import requests as rq
from app.database.cache import (
    cart_cache,
    catalog_cache,
)  # Добавил catalog_cache для get_categories
import logging
from typing import Optional, Union  # Добавил Union для типизации

from app import config as app_config

logger = logging.getLogger(__name__)

privacy_keyboard = InlineKeyboardMarkup(
    inline_keyboard=[
        [
            InlineKeyboardButton(
                text="📜 Политика конфиденциальности", url=app_config.PRIVACY_URL
            )
        ],
        [InlineKeyboardButton(text="✅ Согласиться", callback_data="privacy_accept")],
    ]
)

menu = InlineKeyboardMarkup(
    inline_keyboard=[
        [InlineKeyboardButton(text="Каталог 📦", callback_data="catalog")],
        [
            InlineKeyboardButton(text="Поиск 🔎", callback_data="search_start")
        ],  # Кнопка поиска
        [InlineKeyboardButton(text="🛒 Корзина", callback_data="cart")],
        [
            InlineKeyboardButton(
                text="👨‍💼 Связаться с поддержкой", url=app_config.SUPPORT_URL
            )
        ],
        [InlineKeyboardButton(text="Информация о магазине ℹ️", callback_data="about")],
    ]
)


async def categories_keyboard_builder():
    # Эта функция может быть устаревшей, get_catalog_keyboard используется чаще
    all_categories_data = await rq.get_categories()
    builder = InlineKeyboardBuilder()
    if all_categories_data:
        for category_data in all_categories_data:
            builder.row(
                InlineKeyboardButton(
                    text=category_data["name"],
                    callback_data=f"category:{category_data['name']}:page:1",  # Добавил page:1 для консистентности
                )
            )
    builder.row(InlineKeyboardButton(text="На главную", callback_data="start"))
    return builder.as_markup()


# Эта функция, возможно, не используется или устарела, т.к. есть get_items_keyboard
# async def get_items_by_category_kb(category_name: str):
#     all_items_data = await rq.get_items_by_category(category_name)
#     builder = InlineKeyboardBuilder()
#     if all_items_data:
#         for item_data in all_items_data:
#             builder.row(InlineKeyboardButton(
#                 text=item_data['name'],
#                 callback_data=f"item:{item_data['id']}:category:{category_name}:1" # Обновлен callback_data
#                 ))
#     builder.row(InlineKeyboardButton(text='К категориям', callback_data='catalog'))
#     return builder.as_markup()


def get_items_keyboard(
    items: list, category_name: str, page: int = 1, items_per_page: int = 10
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    start_idx = (page - 1) * items_per_page
    end_idx = start_idx + items_per_page
    current_page_items = items[start_idx:end_idx]

    for item in current_page_items:
        status_emoji = (
            "🔒" if item["status"] == app_config.ITEM_STATUS_RESERVED else "✅"
        )
        quantity_text = (
            f" ({item['quantity']} {item['unit']})" if item["quantity"] > 0 else ""
        )
        price_str = (
            f"{item['price']:.0f}₽"
            if isinstance(item["price"], (int, float))
            else "Цена?"
        )  # .0f для целых рублей
        button_text = f"{status_emoji} {item['name']} - {price_str}{quantity_text}"

        # Обновляем callback_data для передачи источника (категория)
        callback_data_item = f"item:{item['id']}:category:{category_name}:{page}"
        builder.row(
            InlineKeyboardButton(text=button_text, callback_data=callback_data_item)
        )

    total_pages = (len(items) + items_per_page - 1) // items_per_page
    pagination_row = []

    if page > 1:
        pagination_row.append(
            InlineKeyboardButton(
                text="◀️", callback_data=f"category:{category_name}:page:{page-1}"
            )
        )

    if total_pages > 1:  # Показываем номер страницы, только если их больше одной
        pagination_row.append(
            InlineKeyboardButton(text=f"{page}/{total_pages}", callback_data="ignore")
        )

    if page < total_pages:
        pagination_row.append(
            InlineKeyboardButton(
                text="▶️", callback_data=f"category:{category_name}:page:{page+1}"
            )
        )

    if pagination_row:
        builder.row(*pagination_row)

    builder.row(InlineKeyboardButton(text="◀️ Назад в каталог", callback_data="catalog"))
    return builder.as_markup()


def get_catalog_keyboard(categories: list = None) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    if categories:
        for category in categories:
            builder.row(
                InlineKeyboardButton(
                    text=category["name"],
                    callback_data=f"category:{category['name']}:page:1",
                )
            )
    builder.row(
        InlineKeyboardButton(text="◀️ Назад в главное меню", callback_data="start")
    )
    return builder.as_markup()


def get_item_cart_keyboard(
    item_id: str,
    user_id: int,
    item_data: dict,
    source_type: Optional[str] = None,
    source_details: Optional[dict] = None,
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    current_quantity: Union[int, float] = cart_cache.get_item_quantity(user_id, item_id)
    item_available_quantity = item_data.get("quantity", 0)
    item_status = item_data.get("status")
    item_unit = item_data.get("unit", app_config.ITEM_UNIT_PCS)
    can_add_to_cart = (
        item_status == app_config.ITEM_STATUS_AVAILABLE and item_available_quantity > 0
    )

    if can_add_to_cart:
        if item_unit == app_config.ITEM_UNIT_PCS:  # Для товаров в штуках
            # --- Ряд кнопок с малым шагом (-1, +1) ---
            small_step_buttons = []
            if (
                current_quantity >= 1
            ):  # Показываем кнопку -1, если в корзине хотя бы 1 шт.
                small_step_buttons.append(
                    InlineKeyboardButton(
                        text="-1", callback_data=f"cart:decrease:{item_id}:1"
                    )
                )

            current_display_val = (
                int(current_quantity)
                if isinstance(current_quantity, float)
                else current_quantity
            )
            current_display_text = (
                f"{current_display_val} шт" if current_quantity > 0 else "0 шт"
            )
            small_step_buttons.append(
                InlineKeyboardButton(text=current_display_text, callback_data="ignore")
            )

            if current_quantity < item_available_quantity:  # Можно добавить еще
                small_step_buttons.append(
                    InlineKeyboardButton(
                        text="+1", callback_data=f"cart:increase:{item_id}:1"
                    )
                )

            if (
                small_step_buttons
            ):  # Если есть хоть одна кнопка (обычно всегда будет кнопка с количеством)
                builder.row(*small_step_buttons)

            # --- Ряд кнопок с большим шагом (-5, +5) ---
            large_step_buttons = []
            # Кнопка -5: если в корзине >= 5 штук
            if current_quantity >= 5:
                large_step_buttons.append(
                    InlineKeyboardButton(
                        text="-5", callback_data=f"cart:decrease:{item_id}:5"
                    )
                )

            # Пустышка или разделитель, если нужна симметрия, но не обязательно
            # if current_quantity >=5 and current_quantity + 5 <= item_available_quantity :
            #     large_step_buttons.append(InlineKeyboardButton(text=" ", callback_data="ignore"))

            # Кнопка +5: если можно добавить еще хотя бы 5 штук
            if current_quantity + 5 <= item_available_quantity:
                large_step_buttons.append(
                    InlineKeyboardButton(
                        text="+5", callback_data=f"cart:increase:{item_id}:5"
                    )
                )

            if (
                large_step_buttons
            ):  # Добавляем ряд, только если есть хотя бы одна кнопка большого шага
                builder.row(*large_step_buttons)

        elif item_unit == app_config.ITEM_UNIT_ML:  # Для товаров в миллилитрах
            if current_quantity > 0:
                qty_display_text = (
                    str(int(current_quantity))
                    if isinstance(current_quantity, float)
                    and current_quantity.is_integer()
                    else str(current_quantity)
                )
                builder.row(
                    InlineKeyboardButton(
                        text=f"В корзине: {qty_display_text} мл", callback_data="ignore"
                    ),
                    InlineKeyboardButton(
                        text="Сбросить", callback_data=f"cart:reset:{item_id}"
                    ),
                )

            specific_order_steps = item_data.get("order_steps")
            order_steps_to_use = []
            if (
                specific_order_steps
                and isinstance(specific_order_steps, list)
                and len(specific_order_steps) > 0
            ):
                order_steps_to_use = [
                    s
                    for s in specific_order_steps
                    if isinstance(s, (int, float)) and s > 0
                ]
            else:
                order_steps_to_use = [1, 2, 3, 5, 10]

            step_buttons_row1 = []
            step_buttons_row2 = []
            for i, step in enumerate(order_steps_to_use):
                if current_quantity + step <= item_available_quantity:
                    step_text = (
                        str(int(step))
                        if isinstance(step, float) and step.is_integer()
                        else str(step)
                    )
                    btn = InlineKeyboardButton(
                        text=f"+{step_text}мл",
                        callback_data=f"cart:increase:{item_id}:{step}",
                    )
                    if len(step_buttons_row1) < 3:
                        step_buttons_row1.append(btn)
                    else:
                        step_buttons_row2.append(btn)
            if step_buttons_row1:
                builder.row(*step_buttons_row1)
            if step_buttons_row2:
                builder.row(*step_buttons_row2)
    else:
        if item_status == app_config.ITEM_STATUS_RESERVED:
            builder.row(
                InlineKeyboardButton(text="🔒 Забронирован", callback_data="ignore")
            )
        elif item_available_quantity <= 0:
            builder.row(
                InlineKeyboardButton(text="Нет в наличии", callback_data="ignore")
            )

        if current_quantity > 0:
            qty_display_text = ""
            unit_display_text = "мл" if item_unit == app_config.ITEM_UNIT_ML else "шт"

            if isinstance(current_quantity, float):
                qty_display_text = (
                    str(int(current_quantity))
                    if current_quantity.is_integer()
                    else str(current_quantity)
                )
            else:
                qty_display_text = str(current_quantity)

            if not can_add_to_cart:
                builder.row(
                    InlineKeyboardButton(
                        text=f"В корзине: {qty_display_text} {unit_display_text} (нет в наличии)",
                        callback_data="ignore",
                    )
                )

            if item_unit == app_config.ITEM_UNIT_ML:
                builder.row(
                    InlineKeyboardButton(
                        text="Сбросить из корзины",
                        callback_data=f"cart:reset:{item_id}",
                    )
                )
            elif item_unit == app_config.ITEM_UNIT_PCS:
                decrease_amount = (
                    int(current_quantity)
                    if isinstance(current_quantity, float)
                    else current_quantity
                )
                builder.row(
                    InlineKeyboardButton(
                        text="Убрать из корзины",
                        callback_data=f"cart:decrease:{item_id}:{decrease_amount}",
                    )
                )

    builder.row(InlineKeyboardButton(text="🛒 Корзина", callback_data="cart"))

    if source_type == "category" and source_details and "name" in source_details:
        category_name_for_back = source_details["name"]
        page_for_back = source_details.get("page", 1)
        builder.row(
            InlineKeyboardButton(
                text="◀️ Назад к категории",
                callback_data=f"category:{category_name_for_back}:page:{page_for_back}",
            )
        )
    elif (
        source_type == "search_results" and source_details and "query" in source_details
    ):
        query_for_back = source_details["query"]
        page_for_back = source_details.get("page", 1)
        builder.row(
            InlineKeyboardButton(
                text="◀️ Назад к результатам поиска",
                callback_data=f"search_page:{query_for_back}:{page_for_back}",
            )
        )
    else:
        category_name_from_item = item_data.get("category_name")
        if category_name_from_item:
            builder.row(
                InlineKeyboardButton(
                    text="◀️ Назад к категории",
                    callback_data=f"category:{category_name_from_item}:page:1",
                )
            )
        else:
            builder.row(
                InlineKeyboardButton(text="◀️ Назад в каталог", callback_data="catalog")
            )

    return builder.as_markup()


def get_cart_items_keyboard(cart_items: list = None) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    if cart_items:
        for item in cart_items:
            builder.row(
                InlineKeyboardButton(
                    text=f"❌ {item['name']} - {item['quantity']} {item['unit']}",
                    callback_data=f"cart:remove:{item['id']}",
                )
            )
        builder.row(
            InlineKeyboardButton(text="🗑 Очистить корзину", callback_data="cart:clear"),
            InlineKeyboardButton(text="Оформить заказ 🛍️", callback_data="order"),
        )
        builder.row(
            InlineKeyboardButton(
                text="◀️ Продолжить покупки (в каталог)", callback_data="catalog"
            )
        )
    else:  # Корзина пуста
        builder.row(InlineKeyboardButton(text=" каталог", callback_data="catalog"))
        builder.row(
            InlineKeyboardButton(text="◀️ Назад в главное меню", callback_data="start")
        )

    return builder.as_markup()


# --- SEARCH KEYBOARDS ---
def get_cancel_search_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="Отмена", callback_data="cancel_search"))
    # Можно добавить кнопку "Назад в меню", если пользователь передумал искать
    builder.row(
        InlineKeyboardButton(text="◀️ Назад в главное меню", callback_data="start")
    )
    return builder.as_markup()


def get_search_results_keyboard(
    items: list, query_term: str, page: int = 1, items_per_page: int = 5
) -> InlineKeyboardMarkup:
    # items_per_page можно сделать меньше для результатов поиска
    builder = InlineKeyboardBuilder()

    start_idx = (page - 1) * items_per_page
    end_idx = start_idx + items_per_page
    current_page_items = items[start_idx:end_idx]

    for item in current_page_items:
        status_emoji = (
            "🔒" if item["status"] == app_config.ITEM_STATUS_RESERVED else "✅"
        )
        quantity_text = (
            f" ({item['quantity']} {item['unit']})" if item["quantity"] > 0 else ""
        )
        price_str = (
            f"{item['price']:.0f}₽"
            if isinstance(item["price"], (int, float))
            else "Цена?"
        )
        button_text = f"{status_emoji} {item['name']} - {price_str}{quantity_text}"

        # Передаем источник (поиск) и детали для возврата
        callback_data_item = f"item:{item['id']}:search_results:{query_term}:{page}"
        builder.row(
            InlineKeyboardButton(text=button_text, callback_data=callback_data_item)
        )

    total_pages = (len(items) + items_per_page - 1) // items_per_page
    pagination_row = []

    if page > 1:
        pagination_row.append(
            InlineKeyboardButton(
                text="◀️", callback_data=f"search_page:{query_term}:{page-1}"
            )
        )
    if total_pages > 1:
        pagination_row.append(
            InlineKeyboardButton(text=f"{page}/{total_pages}", callback_data="ignore")
        )
    if page < total_pages:
        pagination_row.append(
            InlineKeyboardButton(
                text="▶️", callback_data=f"search_page:{query_term}:{page+1}"
            )
        )

    if pagination_row:
        builder.row(*pagination_row)

    builder.row(
        InlineKeyboardButton(text="Новый поиск 🔎", callback_data="search_start")
    )
    builder.row(
        InlineKeyboardButton(text="◀️ Назад в главное меню", callback_data="start")
    )

    return builder.as_markup()


# --- END SEARCH KEYBOARDS ---


def get_admin_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="📊 Статистика", callback_data="admin:stats"))
    builder.row(
        InlineKeyboardButton(text="🔄 Синхронизация кэша", callback_data="admin:sync")
    )
    builder.row(
        InlineKeyboardButton(text="◀️ Назад в главное меню", callback_data="start")
    )
    return builder.as_markup()
