# app/handlers.py
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import CommandStart
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
import logging

from app.database import requests as rq
from app.database.cache import cart_cache

from app.keyboards_order import get_back_to_cart_keyboard, get_payment_keyboard
from app import config as app_config

router = Router()
logger = logging.getLogger(__name__)


class OrderStates(StatesGroup):
    """Состояния для процесса оформления заказа."""

    waiting_for_name = State()
    waiting_for_phone = State()
    waiting_for_email = State()
    waiting_for_city = State()
    waiting_for_street = State()
    waiting_for_postal_code = State()
    waiting_for_comment = State()
    waiting_for_confirmation = State()
    waiting_for_payment = State()


async def show_order_summary(message: Message, order_data: dict, cart: dict) -> None:
    """Показывает итоговую информацию о заказе."""
    text = "<b>📋 Итоговая информация о заказе:</b>\n\n"
    text += f"<b>ФИО:</b> {order_data['name']}\n"
    text += f"<b>Телефон:</b> {order_data['phone']}\n"
    text += f"<b>Email:</b> {order_data['email']}\n"
    text += f"<b>Адрес:</b> {order_data['city']}, {order_data['street']}, {order_data['postal_code']}\n"
    if order_data.get("comment"):
        text += f"<b>Комментарий:</b> {order_data['comment']}\n\n"

    # Добавляем информацию о товарах
    text += "<b>Товары в заказе:</b>\n"
    total_price = 0
    for item_id, quantity in cart.items():
        item_data = await rq.get_item(item_id)
        if item_data:
            item_total = item_data["price"] * quantity
            total_price += item_total
            text += f"• {item_data['name']} - {quantity} {item_data['unit']} ({item_total:.2f} руб.)\n"

    text += f"\n<b>Итого к оплате:</b> {total_price:.2f} руб."

    await message.answer(text, reply_markup=get_payment_keyboard(), parse_mode="HTML")


@router.callback_query(F.data == "order")
async def start_order(callback: CallbackQuery, state: FSMContext):
    """Начало процесса оформления заказа."""
    cart = cart_cache.get_cart(callback.from_user.id)
    if not cart:
        await callback.answer("Ваша корзина пуста!", show_alert=True)
        return

    # Проверяем, есть ли сохраненные данные
    saved_data = await rq.get_user_order_data(callback.from_user.id)
    if saved_data:
        # Если есть сохраненные данные, показываем их и предлагаем использовать
        await state.set_data(saved_data)
        await show_order_summary(callback.message, saved_data, cart)
        await state.set_state(OrderStates.waiting_for_payment)
    else:
        # Если нет сохраненных данных, начинаем процесс ввода
        await state.set_state(OrderStates.waiting_for_name)
        await callback.message.edit_text(
            "Для оформления заказа, пожалуйста, введите ваше ФИО:",
            reply_markup=get_back_to_cart_keyboard(),
        )


@router.callback_query(F.data == "order:edit")
async def edit_order_data(callback: CallbackQuery, state: FSMContext):
    """Начало редактирования данных заказа."""
    await state.set_state(OrderStates.waiting_for_name)
    await callback.message.edit_text(
        "Введите ваше ФИО:", reply_markup=get_back_to_cart_keyboard()
    )


@router.message(OrderStates.waiting_for_name)
async def process_name(message: Message, state: FSMContext):
    """Обработка ввода имени."""
    await state.update_data(name=message.text)
    await state.set_state(OrderStates.waiting_for_phone)
    await message.answer(
        "Введите ваш номер телефона:", reply_markup=get_back_to_cart_keyboard()
    )


@router.message(OrderStates.waiting_for_phone)
async def process_phone(message: Message, state: FSMContext):
    """Обработка ввода телефона."""
    await state.update_data(phone=message.text)
    await state.set_state(OrderStates.waiting_for_email)
    await message.answer("Введите ваш email:", reply_markup=get_back_to_cart_keyboard())


@router.message(OrderStates.waiting_for_email)
async def process_email(message: Message, state: FSMContext):
    """Обработка ввода email."""
    await state.update_data(email=message.text)
    await state.set_state(OrderStates.waiting_for_city)
    await message.answer(
        "Введите город доставки:", reply_markup=get_back_to_cart_keyboard()
    )


@router.message(OrderStates.waiting_for_city)
async def process_city(message: Message, state: FSMContext):
    """Обработка ввода города."""
    await state.update_data(city=message.text)
    await state.set_state(OrderStates.waiting_for_street)
    await message.answer(
        "Введите улицу и номер дома:", reply_markup=get_back_to_cart_keyboard()
    )


@router.message(OrderStates.waiting_for_street)
async def process_street(message: Message, state: FSMContext):
    """Обработка ввода улицы."""
    await state.update_data(street=message.text)
    await state.set_state(OrderStates.waiting_for_postal_code)
    await message.answer(
        "Введите почтовый индекс:", reply_markup=get_back_to_cart_keyboard()
    )


@router.message(OrderStates.waiting_for_postal_code)
async def process_postal_code(message: Message, state: FSMContext):
    """Обработка ввода почтового индекса."""
    await state.update_data(postal_code=message.text)
    await state.set_state(OrderStates.waiting_for_comment)
    await message.answer(
        "Введите комментарий к заказу (или отправьте '-' если комментарий не нужен):",
        reply_markup=get_back_to_cart_keyboard(),
    )


@router.message(OrderStates.waiting_for_comment)
async def process_comment(message: Message, state: FSMContext):
    """Обработка ввода комментария и показ итоговой информации."""
    comment = message.text if message.text != "-" else ""
    await state.update_data(comment=comment)

    # Получаем все данные заказа
    order_data = await state.get_data()
    cart = cart_cache.get_cart(message.from_user.id)

    # Сохраняем данные заказа
    await rq.save_user_order_data(message.from_user.id, order_data)

    # Показываем итоговую информацию
    await show_order_summary(message, order_data, cart)
    await state.set_state(OrderStates.waiting_for_payment)


@router.callback_query(F.data.startswith("payment:"))
async def process_payment(callback: CallbackQuery, state: FSMContext):
    """Обработка выбора способа оплаты."""
    payment_method = callback.data.split(":")[1]

    if payment_method == "card":
        await callback.message.edit_text(
            "💳 Оплата картой\n\n" "Функция в разработке...",
            reply_markup=get_back_to_cart_keyboard(),
        )
    elif payment_method == "sbp":
        await callback.message.edit_text(
            "🏦 Оплата СБП\n\n" "Функция в разработке...",
            reply_markup=get_back_to_cart_keyboard(),
        )

    await callback.answer()
