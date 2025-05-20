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
from app.keyboards import (
    menu as menu_keyboard,
    categories_keyboard_builder,
    get_items_by_category_kb,
    back_to_category_kb,
    privacy_keyboard,
    get_catalog_keyboard,
    get_items_keyboard,
    get_cart_keyboard,
    get_item_cart_keyboard,
    get_cart_items_keyboard,
    get_admin_keyboard
)
from app import config as app_config

router = Router()
logger = logging.getLogger(__name__)

@router.message(CommandStart())
async def cmd_start(message: Message):
    try:
        await rq.set_user(message.from_user.id)
        privacy_accepted = await rq.get_user_privacy_status(message.from_user.id)
        
        # Отправляем приветственное сообщение
        await message.answer(app_config.WELCOME_MESSAGE)
        
        if not privacy_accepted:
            await message.answer(
                'Для использования бота необходимо согласиться с политикой конфиденциальности.',
                reply_markup=privacy_keyboard
            )
        else:
            await message.answer('Добро пожаловать в Perfume Shop!', reply_markup=menu_keyboard)
    except Exception as e:
        logger.error(f"Error in cmd_start for user {message.from_user.id}: {e}", exc_info=True)
        await message.answer("Произошла ошибка при обработке вашего запроса. Попробуйте позже.")

@router.callback_query(F.data == 'privacy_accept')
async def privacy_accept_handler(callback: CallbackQuery):
    try:
        logger.info(f"User {callback.from_user.id} pressed button: {callback.data}")
        await callback.answer('')
        await rq.accept_privacy_policy(callback.from_user.id)
        await callback.message.edit_text('Спасибо за согласие! Теперь вы можете использовать бота.', reply_markup=menu_keyboard)
    except Exception as e:
        logger.error(f"Error in privacy_accept_handler for user {callback.from_user.id}: {e}", exc_info=True)
        await callback.message.answer("Произошла ошибка при обработке вашего согласия. Попробуйте позже.")
        await callback.answer("Ошибка", show_alert=True)

# Добавляем проверку согласия для всех остальных обработчиков
async def check_privacy_accepted(callback: CallbackQuery) -> bool:
    """Проверяет, согласился ли пользователь с политикой конфиденциальности."""
    try:
        privacy_accepted = await rq.get_user_privacy_status(callback.from_user.id)
        if not privacy_accepted:
            await callback.answer('Сначала необходимо согласиться с политикой конфиденциальности.', show_alert=True)
            await callback.message.answer(
                'Для использования бота необходимо согласиться с политикой конфиденциальности.',
                reply_markup=privacy_keyboard
            )
            return False
        return True
    except Exception as e:
        logger.error(f"Error checking privacy status for user {callback.from_user.id}: {e}", exc_info=True)
        return False

@router.callback_query(F.data == "catalog")
async def catalog_handler(callback: CallbackQuery):
    """Обработчик кнопки каталога."""
    logger.info(f"User {callback.from_user.id} pressed button: {callback.data}")
    if not await check_privacy_accepted(callback):
        return

    categories = await rq.get_categories()
    if not categories:
        await callback.message.edit_text(
            "Каталог временно недоступен.",
            reply_markup=menu_keyboard
        )
        return

    keyboard = get_catalog_keyboard(categories)
    await callback.message.edit_text(
        "Выберите категорию:",
        reply_markup=keyboard
    )

@router.callback_query(F.data.startswith("category:"))
async def category_items_handler(callback: CallbackQuery):
    """Обработчик выбора категории с поддержкой пагинации."""
    logger.info(f"User {callback.from_user.id} pressed button: {callback.data}")
    if not await check_privacy_accepted(callback):
        return

    # Парсим данные из callback_data
    # Формат: category:category_name:page:page_number
    parts = callback.data.split(":")
    category_name = parts[1]
    page = int(parts[3]) if len(parts) > 3 else 1

    # Получаем товары категории
    items = await rq.get_items_by_category(category_name)
    
    if not items:
        await callback.message.edit_text(
            "В данной категории пока нет товаров.",
            reply_markup=get_catalog_keyboard()
        )
        return

    # Создаем клавиатуру с пагинацией
    keyboard = get_items_keyboard(items, category_name, page)
    
    # Формируем текст сообщения
    message_text = f"Категория: {category_name}\n\nВыберите товар:"
    
    # Проверяем, есть ли у текущего сообщения изображение
    if callback.message.photo:
        # Если есть изображение, отправляем новое сообщение и удаляем старое
        await callback.message.answer(message_text, reply_markup=keyboard)
        await callback.message.delete()
    else:
        # Если нет изображения, редактируем существующее сообщение
        await callback.message.edit_text(message_text, reply_markup=keyboard)

@router.callback_query(F.data == "ignore")
async def ignore_handler(callback: CallbackQuery):
    """Обработчик для игнорирования нажатий на неактивные кнопки."""
    logger.info(f"User {callback.from_user.id} pressed button: {callback.data}")
    await callback.answer()

@router.callback_query(F.data.startswith('item:'))
async def item_handler(callback: CallbackQuery):
    logger.info(f"User {callback.from_user.id} pressed button: {callback.data}")
    if not await check_privacy_accepted(callback):
        return
    try:
        item_id = callback.data.split(':', 1)[1]
        await callback.answer('')
        item_data = await rq.get_item(item_id)
        print(item_data)

        if item_data:
            # Формируем информацию о статусе и наличии
            status_emoji = "🔒" if item_data['status'] == app_config.ITEM_STATUS_RESERVED else "✅"
            status_text = "Забронирован" if item_data['status'] == app_config.ITEM_STATUS_RESERVED else "Доступен"
            quantity_text = f"\n<b>В наличии:</b> {item_data['quantity']} {item_data['unit']}" if item_data['quantity'] > 0 else "\n<b>В наличии:</b> Нет"
            
            price_str = f"{item_data['price']:.2f} руб." if isinstance(item_data.get('price'), (int, float)) else "Цена не указана"
            text = (f"<b>{item_data.get('name', 'Без названия')}</b>\n\n"
                    f"{item_data.get('description', 'Описание отсутствует.')}\n\n"
                    f"<b>Цена:</b> {price_str}\n"
                    f"<b>Статус:</b> {status_emoji} {status_text}"
                    f"{quantity_text}")
            
            # Добавляем информацию о количестве в корзине
            cart_quantity = cart_cache.get_item_quantity(callback.from_user.id, item_id)
            if cart_quantity > 0:
                text += f"\n\n<b>В корзине:</b> {cart_quantity} {item_data['unit']}"
            
            category_name_for_back_button = item_data.get('category_name')
            
            # Получаем номер страницы из предыдущего сообщения
            page = 1
            if callback.message.text and "Категория:" in callback.message.text:
                try:
                    items = await rq.get_items_by_category(category_name_for_back_button)
                    item_index = next((i for i, item in enumerate(items) if item['id'] == item_id), -1)
                    if item_index != -1:
                        page = (item_index // 10) + 1
                except Exception as e:
                    logger.error(f"Error calculating page number: {e}")
            
            # Создаем клавиатуру с кнопками управления корзиной
            reply_markup = get_item_cart_keyboard(item_id, callback.from_user.id, item_data)

            if item_data.get('image_url'):
                await callback.message.answer_photo(
                    photo=item_data['image_url'],
                    caption=text,
                    reply_markup=reply_markup,
                    parse_mode="HTML"
                )
                await callback.message.delete()
            else:
                await callback.message.edit_text(text, reply_markup=reply_markup, parse_mode="HTML")
        else:
            await callback.message.edit_text('Товар не найден.', reply_markup=await categories_keyboard_builder())
            await callback.answer("Товар не найден", show_alert=True)
    except Exception as e:
        logger.error(f"Error in item_handler for item '{callback.data}': {e}", exc_info=True)
        await callback.message.answer("Не удалось загрузить информацию о товаре.")
        await callback.answer("Ошибка загрузки", show_alert=True)

@router.callback_query(F.data == 'about')
async def contacts_handler(callback: CallbackQuery):
    logger.info(f"User {callback.from_user.id} pressed button: {callback.data}")
    if not await check_privacy_accepted(callback):
        return
    await callback.answer('')
    keyboard = get_catalog_keyboard()
    await callback.message.edit_text(
        app_config.ABOUT,
        reply_markup=keyboard
    )

@router.callback_query(F.data == 'start')
async def back_to_main_menu_handler(callback: CallbackQuery):
    logger.info(f"User {callback.from_user.id} pressed button: {callback.data}")
    if not await check_privacy_accepted(callback):
        return
    try:
        await callback.answer('')
        await callback.message.edit_text('Добро пожаловать в Perfume Shop!', reply_markup=menu_keyboard)
    except Exception as e:
        logger.error(f"Error in back_to_main_menu_handler: {e}", exc_info=True)
        await callback.message.answer("Произошла ошибка. Попробуйте позже.")
        await callback.answer("Ошибка", show_alert=True)

@router.callback_query(F.data == "cart")
async def cart_handler(callback: CallbackQuery):
    """Обработчик просмотра корзины."""
    logger.info(f"User {callback.from_user.id} pressed button: {callback.data}")
    if not await check_privacy_accepted(callback):
        return
    
    cart = cart_cache.get_cart(callback.from_user.id)
    if cart:
        # Получаем информацию о товарах в корзине
        cart_items = []
        total_price = 0
        for item_id, quantity in cart.items():
            item_data = await rq.get_item(item_id)
            if item_data:
                cart_items.append({
                    'id': item_id,
                    'name': item_data['name'],
                    'quantity': quantity,
                    'unit': item_data['unit'],
                    'price': item_data['price']
                })
                total_price += item_data['price'] * quantity
        
        # Формируем текст сообщения
        text = "<b>🛒 Ваша корзина:</b>\n\n"
        for item in cart_items:
            text += f"• {item['name']} - {item['quantity']} {item['unit']} ({item['price'] * item['quantity']:.2f} руб.)\n"
        text += f"\n<b>Итого:</b> {total_price:.2f} руб."
    else:
        await callback.message.edit_text(
        "Ваша корзина пуста.",
        reply_markup=get_cart_items_keyboard(),
        parse_mode="HTML")
        return
    # Отправляем сообщение с клавиатурой
    await callback.message.edit_text(
        text,
        reply_markup=get_cart_items_keyboard(cart_items),
        parse_mode="HTML"
    )

@router.callback_query(F.data.startswith("cart:"))
async def cart_action_handler(callback: CallbackQuery):
    """Обработчик действий с корзиной."""
    logger.info(f"User {callback.from_user.id} pressed button: {callback.data}")
    if not await check_privacy_accepted(callback):
        return
    
    try:
        # Разбираем callback_data: cart:increase:item_id:amount
        _, action, *params = callback.data.split(":")
        
        if action == "increase":
            item_id, amount = params
            amount = float(amount)  # Для мл используем float
            current_quantity = cart_cache.get_item_quantity(callback.from_user.id, item_id)
            
            # Получаем информацию о товаре для проверки доступного количества
            item_data = await rq.get_item(item_id)
            if not item_data:
                await callback.answer("Товар не найден", show_alert=True)
                return
                
            available_quantity = item_data['quantity']
            # Вычисляем, сколько товара можно добавить
            can_add = available_quantity - current_quantity
            # Берем минимальное из запрошенного количества и доступного
            amount_to_add = min(amount, can_add)
            
            if amount_to_add > 0:
                cart_cache.add_to_cart(callback.from_user.id, item_id, current_quantity + amount_to_add)
            else:
                await callback.answer("Достигнуто максимальное доступное количество", show_alert=True)
                return
            
        elif action == "decrease":
            item_id, amount = params
            amount = int(amount)
            current_quantity = cart_cache.get_item_quantity(callback.from_user.id, item_id)
            # Убеждаемся, что новое количество не будет меньше 0
            new_quantity = max(0, current_quantity - amount)
            cart_cache.add_to_cart(callback.from_user.id, item_id, new_quantity)
            
        elif action == "reset":
            item_id = params[0]
            cart_cache.remove_from_cart(callback.from_user.id, item_id)
            
        elif action == "remove":
            item_id = params[0]
            cart_cache.remove_from_cart(callback.from_user.id, item_id)
            
        elif action == "clear":
            cart_cache.clear_cart(callback.from_user.id)
            await callback.message.edit_text(
                "Корзина очищена.",
                reply_markup=menu_keyboard
            )
            return
        
        # Обновляем сообщение с товаром
        item_id = params[0]
        item_data = await rq.get_item(item_id)
        if item_data:
            # Обновляем информацию о товаре
            status_emoji = "🔒" if item_data['status'] == app_config.ITEM_STATUS_RESERVED else "✅"
            status_text = "Забронирован" if item_data['status'] == app_config.ITEM_STATUS_RESERVED else "Доступен"
            quantity_text = f"\n<b>В наличии:</b> {item_data['quantity']} {item_data['unit']}" if item_data['quantity'] > 0 else "\n<b>В наличии:</b> Нет"
            
            price_str = f"{item_data['price']:.2f} руб." if isinstance(item_data.get('price'), (int, float)) else "Цена не указана"
            text = (f"<b>{item_data.get('name', 'Без названия')}</b>\n\n"
                    f"{item_data.get('description', 'Описание отсутствует.')}\n\n"
                    f"<b>Цена:</b> {price_str}\n"
                    f"<b>Статус:</b> {status_emoji} {status_text}"
                    f"{quantity_text}")
            
            # Добавляем информацию о количестве в корзине
            cart_quantity = cart_cache.get_item_quantity(callback.from_user.id, item_id)
            if cart_quantity > 0:
                text += f"\n\n<b>В корзине:</b> {cart_quantity} {item_data['unit']}"
            
            await callback.message.edit_text(
                text,
                reply_markup=get_item_cart_keyboard(item_id, callback.from_user.id, item_data),
                parse_mode="HTML"
            )
        
        await callback.answer()
        
    except Exception as e:
        logger.error(f"Error in cart_action_handler: {e}", exc_info=True)
        await callback.answer("Произошла ошибка при обработке действия с корзиной", show_alert=True)
def is_admin(user_id: int) -> bool:
    """Проверяет, является ли пользователь администратором."""
    return user_id in app_config.ADMIN_IDS
@router.message(Command("admin"))
async def admin_command(message: Message):
    """Обработчик команды /admin."""
    if not is_admin(message.from_user.id):
        return
    
    await message.answer(
        "Панель администратора",
        reply_markup=get_admin_keyboard()
    )

@router.callback_query(lambda c: c.data.startswith("admin:"))
async def process_admin_callback(callback: CallbackQuery):
    """Обработчик callback-запросов от админ-кнопок."""
    if not is_admin(callback.from_user.id):
        await callback.answer("У вас нет доступа к этой функции.", show_alert=True)
        return
    
    action = callback.data.split(":")[1]
    
    if action == "stats":
        await callback.message.edit_text(
            "📊 Статистика\n\nФункция в разработке...",
            reply_markup=get_admin_keyboard()
        )
    elif action == "sync":
        await callback.message.edit_text(
            "🔄 Синхронизация\n\nФункция в разработке...",
            reply_markup=get_admin_keyboard()
        )
    
    await callback.answer()