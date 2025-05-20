# app/keyboards_order.py
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder


def get_back_to_cart_keyboard() -> InlineKeyboardMarkup:
    """Создает клавиатуру с кнопкой возврата в корзину."""
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="◀️ Вернуться в корзину", callback_data="cart")
    )
    return builder.as_markup()


def get_payment_keyboard() -> InlineKeyboardMarkup:
    """Создает клавиатуру с кнопками оплаты."""
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="💳 Оплатить картой", callback_data="payment:card")
    )
    builder.row(
        InlineKeyboardButton(text="🏦 Оплатить СБП", callback_data="payment:sbp")
    )
    builder.row(
        InlineKeyboardButton(text="✏️ Изменить данные", callback_data="order:edit")
    )
    builder.row(
        InlineKeyboardButton(text="◀️ Вернуться в корзину", callback_data="cart")
    )
    return builder.as_markup()
