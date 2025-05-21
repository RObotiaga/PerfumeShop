# app/handlers.py
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
import logging
from typing import Optional # Добавим Optional
from aiogram.exceptions import TelegramBadRequest

from app.database import requests as rq
from app.database.cache import cart_cache
from app.keyboards import (
    menu as menu_keyboard,
    categories_keyboard_builder,
    # get_items_by_category_kb, # Возможно, устарело
    # back_to_category_kb, # Возможно, устарело
    privacy_keyboard,
    get_catalog_keyboard,
    get_items_keyboard,
    # get_cart_keyboard, # Не используется напрямую, часть других клавиатур
    get_item_cart_keyboard,
    get_cart_items_keyboard,
    get_admin_keyboard,
    get_cancel_search_keyboard,  # Новая клавиатура
    get_search_results_keyboard, # Новая клавиатура
)
from app import config as app_config

router = Router()
logger = logging.getLogger(__name__)


# Определяем состояния для поиска
class SearchStates(StatesGroup):
    waiting_for_query = State()


@router.message(CommandStart())
async def cmd_start(message: Message):
    try:
        await rq.set_user(message.from_user.id)
        privacy_accepted = await rq.get_user_privacy_status(message.from_user.id)
        
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

async def check_privacy_accepted(callback_or_message: Message | CallbackQuery) -> bool: # Обновлено для Message или CallbackQuery
    """Проверяет, согласился ли пользователь с политикой конфиденциальности."""
    user_id = callback_or_message.from_user.id
    try:
        privacy_accepted = await rq.get_user_privacy_status(user_id)
        if not privacy_accepted:
            message_target = callback_or_message.message if isinstance(callback_or_message, CallbackQuery) else callback_or_message
            if isinstance(callback_or_message, CallbackQuery):
                 await callback_or_message.answer('Сначала необходимо согласиться с политикой конфиденциальности.', show_alert=True)

            await message_target.answer(
                'Для использования бота необходимо согласиться с политикой конфиденциальности.',
                reply_markup=privacy_keyboard
            )
            return False
        return True
    except Exception as e:
        logger.error(f"Error checking privacy status for user {user_id}: {e}", exc_info=True)
        return False

@router.callback_query(F.data == "catalog")
async def catalog_handler(callback: CallbackQuery):
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
    logger.info(f"User {callback.from_user.id} pressed button: {callback.data}")
    if not await check_privacy_accepted(callback):
        return

    parts = callback.data.split(":")
    category_name = parts[1]
    page = int(parts[3]) if len(parts) > 3 else 1

    items = await rq.get_items_by_category(category_name)
    
    if not items:
        all_categories = await rq.get_categories()
        try:
            await callback.message.edit_text(
                "В данной категории пока нет товаров.",
                reply_markup=get_catalog_keyboard(all_categories)
            )
        except TelegramBadRequest as e:
            if "message is not modified" in str(e):
                logger.debug("Message not modified (no items in category), ignoring.")
                pass # Игнорируем, если сообщение не изменилось
            else:
                raise # Перевыбрасываем другие ошибки TelegramBadRequest
        await callback.answer() # Отвечаем на callback в любом случае
        return

    keyboard = get_items_keyboard(items, category_name, page)
    message_text = f"Категория: {category_name}\n\nВыберите товар:"
    
    try:
        if callback.message.photo:
            # Если предыдущее сообщение было с фото, а новое - список товаров (текст),
            # то удаляем старое и отправляем новое.
            await callback.message.delete()
            await callback.message.answer(message_text, reply_markup=keyboard)
        else:
            # Если предыдущее сообщение было текстовым, пытаемся его отредактировать.
            await callback.message.edit_text(message_text, reply_markup=keyboard)
    except TelegramBadRequest as e:
        if "message is not modified" in str(e):
            logger.debug("Message not modified (category items), ignoring.")
            pass # Игнорируем, если сообщение не изменилось
        else:
            logger.error(f"TelegramBadRequest in category_items_handler: {e}", exc_info=True)
            # Можно отправить новое сообщение, если редактирование не удалось по другой причине
            # await callback.message.answer(message_text, reply_markup=keyboard)
            # await callback.message.delete() # Удалить старое, если отправлено новое
            raise # Или просто перевыбросить ошибку для отладки
    except Exception as e_main:
        logger.error(f"Error in category_items_handler editing/sending message: {e_main}", exc_info=True)
        # Обработка других возможных ошибок

    await callback.answer()
@router.callback_query(F.data == "ignore")
async def ignore_handler(callback: CallbackQuery):
    logger.info(f"User {callback.from_user.id} pressed button: {callback.data}")
    await callback.answer()

@router.callback_query(F.data.startswith('item:'))
async def item_handler(callback: CallbackQuery):
    logger.info(f"User {callback.from_user.id} pressed button: {callback.data}")
    if not await check_privacy_accepted(callback):
        return
    try:
        data_parts = callback.data.split(':') # item:item_id:source_type:detail1:detail2...
        item_id = data_parts[1]
        
        source_type: Optional[str] = None
        source_details: dict = {}

        if len(data_parts) > 2:
            source_type = data_parts[2] # category или search_results
            if source_type == "category" and len(data_parts) >= 5: # item:id:category:name:page
                source_details['name'] = data_parts[3]
                try:
                    source_details['page'] = int(data_parts[4])
                except (ValueError, IndexError):
                    source_details['page'] = 1
            elif source_type == "search_results" and len(data_parts) >= 5: # item:id:search_results:query:page
                source_details['query'] = data_parts[3]
                try:
                    source_details['page'] = int(data_parts[4])
                except (ValueError, IndexError):
                    source_details['page'] = 1
            else: # Если формат не распознан, сбрасываем source_type
                source_type = None 
                source_details = {}


        await callback.answer('') # Отвечаем на callback сразу
        item_data = await rq.get_item(item_id)

        if item_data:
            status_emoji = "🔒" if item_data['status'] == app_config.ITEM_STATUS_RESERVED else "✅"
            status_text = "Забронирован" if item_data['status'] == app_config.ITEM_STATUS_RESERVED else "Доступен"
            quantity_text = f"\n<b>В наличии:</b> {item_data['quantity']} {item_data['unit']}" if item_data['quantity'] > 0 else "\n<b>В наличии:</b> Нет"
            
            price_str = f"{item_data['price']:.2f} руб." if isinstance(item_data.get('price'), (int, float)) else "Цена не указана"
            text = (f"<b>{item_data.get('name', 'Без названия')}</b>\n\n"
                    f"{item_data.get('description', 'Описание отсутствует.')}\n\n"
                    f"<b>Цена:</b> {price_str}\n"
                    f"<b>Статус:</b> {status_emoji} {status_text}"
                    f"{quantity_text}")
            
            cart_quantity = cart_cache.get_item_quantity(callback.from_user.id, item_id)
            if cart_quantity > 0:
                text += f"\n\n<b>В корзине:</b> {cart_quantity} {item_data['unit']}"
            
            reply_markup = get_item_cart_keyboard(
                item_id, 
                callback.from_user.id, 
                item_data,
                source_type=source_type,
                source_details=source_details
            )

            if item_data.get('image_url'):
                # Сначала удаляем старое сообщение, потом отправляем новое с фото
                # Это предотвращает "прыгание" интерфейса, если фото отправляется медленно
                if callback.message.photo is None : # если у текущего сообщения нет фото
                     await callback.message.delete()
                await callback.message.answer_photo(
                    photo=item_data['image_url'],
                    caption=text,
                    reply_markup=reply_markup,
                    parse_mode="HTML"
                )
                # Если у старого сообщения было фото, оно УЖЕ удалено этой же логикой ранее,
                # или мы на него ответили и оно заменилось.
                # Если у старого сообщения НЕ БЫЛО фото, а новое с фото, то старое сообщение удаляем.
                # Если старое сообщение было текстовым и новое текстовое, то оно будет отредактировано ниже.
                # Эта логика стала сложнее, нужно убедиться, что она корректна.
                # Проще: если новое сообщение с фото, всегда удаляем старое и отправляем новое.
                if callback.message.text: # если старое сообщение было текстовым
                    try:
                        await callback.message.delete()
                    except Exception as e_del:
                        logger.warning(f"Could not delete previous text message for item photo: {e_del}")

            else:
                # Если новое сообщение текстовое, удаляем предыдущее фото (если оно было)
                if callback.message.photo:
                    try:
                        await callback.message.delete()
                    except Exception as e_del:
                        logger.warning(f"Could not delete previous photo message for item text: {e_del}")
                    await callback.message.answer(text, reply_markup=reply_markup, parse_mode="HTML")
                else: # и старое и новое текстовые - редактируем
                    await callback.message.edit_text(text, reply_markup=reply_markup, parse_mode="HTML")
        else:
            all_categories = await rq.get_categories() # Получаем категории для кнопки "назад"
            await callback.message.edit_text('Товар не найден.', reply_markup=get_catalog_keyboard(all_categories))
            await callback.answer("Товар не найден", show_alert=True) # show_alert для callback.answer
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
    all_categories = await rq.get_categories() # Получаем категории для кнопки "назад"
    await callback.message.edit_text(
        app_config.ABOUT,
        reply_markup=get_catalog_keyboard(all_categories) # Передаем категории
    )

@router.callback_query(F.data == 'start')
async def back_to_main_menu_handler(callback: CallbackQuery, state: FSMContext): # Добавил state
    logger.info(f"User {callback.from_user.id} pressed button: {callback.data}")
    # if not await check_privacy_accepted(callback): # Проверка здесь может быть излишней, если это просто возврат в меню
    #     return
    await state.clear() # Очищаем состояние FSM при возврате в главное меню
    try:
        await callback.answer('')
        await callback.message.edit_text('Добро пожаловать в Perfume Shop!', reply_markup=menu_keyboard)
    except Exception as e:
        logger.error(f"Error in back_to_main_menu_handler: {e}", exc_info=True)
        await callback.message.answer("Произошла ошибка. Попробуйте позже.")
        await callback.answer("Ошибка", show_alert=True)

# --- SEARCH HANDLERS ---
@router.callback_query(F.data == 'search_start')
async def search_start_handler(callback: CallbackQuery, state: FSMContext):
    logger.info(f"User {callback.from_user.id} initiated search.")
    if not await check_privacy_accepted(callback):
        return
    await state.set_state(SearchStates.waiting_for_query)
    await callback.message.edit_text(
        "Введите название товара для поиска (минимум 3 символа):",
        reply_markup=get_cancel_search_keyboard() 
    )
    await callback.answer()

@router.message(SearchStates.waiting_for_query, F.text)
async def process_search_query_handler(message: Message, state: FSMContext):
    query = message.text.strip()
    user_id = message.from_user.id
    
    if not await check_privacy_accepted(message): # Проверка для прямого ввода текста
        await state.clear()
        return

    logger.info(f"User {user_id} submitted search query: '{query}'")

    if len(query) < 3:
        await message.answer(
            "Поисковый запрос слишком короткий. Пожалуйста, введите минимум 3 символа.",
            reply_markup=get_cancel_search_keyboard()
        )
        return

    await state.update_data(search_query=query) # Сохраняем для пагинации
    items = await rq.search_items_by_name(query)

    if not items:
        await message.answer(
            f"По вашему запросу '{query}' ничего не найдено.\nПопробуйте изменить запрос или вернитесь в меню.",
            reply_markup=menu_keyboard 
        )
        await state.clear()
        return

    keyboard = get_search_results_keyboard(items, query, page=1)
    await message.answer(
        f"Результаты поиска по запросу '{query}':",
        reply_markup=keyboard
    )
    await state.clear()

@router.callback_query(F.data == 'cancel_search', SearchStates.waiting_for_query) # Уточняем состояние
async def cancel_search_handler(callback: CallbackQuery, state: FSMContext):
    logger.info(f"User {callback.from_user.id} cancelled search.")
    await state.clear()
    await callback.message.edit_text(
        'Поиск отменен.',
        reply_markup=menu_keyboard
    )
    await callback.answer()

@router.callback_query(F.data.startswith("search_page:"))
async def search_page_handler(callback: CallbackQuery): # state здесь не нужен, если query в callback
    try:
        _, query_term, page_str = callback.data.split(":", 2) # Используем maxsplit=2
        page = int(page_str)
    except ValueError:
        logger.error(f"Invalid search_page callback_data: {callback.data}")
        await callback.answer("Ошибка пагинации.", show_alert=True)
        return

    logger.info(f"User {callback.from_user.id} requested search page {page} for query '{query_term}'")
    
    if not await check_privacy_accepted(callback): # Проверка согласия
        return

    items = await rq.search_items_by_name(query_term) 

    if not items: 
        await callback.message.edit_text(
            "Не удалось загрузить результаты поиска. Возможно, они изменились.",
            reply_markup=menu_keyboard
        )
        await callback.answer()
        return

    keyboard = get_search_results_keyboard(items, query_term, page)
    await callback.message.edit_text(
        f"Результаты поиска по запросу '{query_term}' (Страница {page}):",
        reply_markup=keyboard
    )
    await callback.answer()

# --- END SEARCH HANDLERS ---

@router.callback_query(F.data == "cart")
async def cart_handler(callback: CallbackQuery):
    logger.info(f"User {callback.from_user.id} pressed button: {callback.data}")
    if not await check_privacy_accepted(callback):
        return
    
    cart = cart_cache.get_cart(callback.from_user.id)
    cart_items_details = [] # Изменено имя переменной для ясности
    total_price = 0

    if cart:
        for item_id, quantity in cart.items():
            item_data = await rq.get_item(item_id)
            if item_data:
                cart_items_details.append({ # Используем новое имя
                    'id': item_id,
                    'name': item_data['name'],
                    'quantity': quantity,
                    'unit': item_data['unit'],
                    'price': item_data['price']
                })
                total_price += item_data['price'] * quantity
        
        text = "<b>🛒 Ваша корзина:</b>\n\n"
        if not cart_items_details: # Если товары были в корзине, но не нашлись в базе
             text += "Некоторые товары в вашей корзине не удалось загрузить. Они могли быть удалены."
        else:
            for item_detail in cart_items_details:
                text += f"• {item_detail['name']} - {item_detail['quantity']} {item_detail['unit']} ({item_detail['price'] * item_detail['quantity']:.2f} руб.)\n"
        text += f"\n<b>Итого:</b> {total_price:.2f} руб."
        
        reply_markup = get_cart_items_keyboard(cart_items_details) # Передаем детали товаров
    else:
        text = "Ваша корзина пуста."
        reply_markup = get_cart_items_keyboard() # Без аргументов для пустой корзины

    await callback.message.edit_text(
        text,
        reply_markup=reply_markup,
        parse_mode="HTML"
    )


@router.callback_query(F.data.startswith("cart:"))
async def cart_action_handler(callback: CallbackQuery):
    logger.info(f"User {callback.from_user.id} pressed button: {callback.data}")
    if not await check_privacy_accepted(callback):
        return
    
    try:
        # Убедимся, что на callback ответили, чтобы кнопка не "зависала"
        # Делаем это в начале, если не будет ранних выходов с show_alert=True
        # await callback.answer() # Перенесем ответ ближе к концу, если нет alert

        _, action, *params = callback.data.split(":")
        item_id_for_update: Optional[str] = None 

        if action == "increase":
            item_id, amount_str = params
            item_id_for_update = item_id
            
            item_data = await rq.get_item(item_id)
            if not item_data:
                await callback.answer("Товар не найден", show_alert=True)
                return

            amount: float | int
            if item_data['unit'] == app_config.ITEM_UNIT_ML:
                amount = float(amount_str)
            else: 
                amount = int(amount_str)

            current_quantity = cart_cache.get_item_quantity(callback.from_user.id, item_id)
            available_quantity = item_data['quantity']
            
            # Проверяем, не забронирован ли товар
            if item_data['status'] == app_config.ITEM_STATUS_RESERVED:
                await callback.answer("Товар забронирован и недоступен для заказа.", show_alert=True)
                return

            can_add = available_quantity - current_quantity
            amount_to_add = min(amount, can_add)
            
            if amount_to_add > 0:
                new_cart_quantity = current_quantity + amount_to_add
                if isinstance(new_cart_quantity, float): new_cart_quantity = round(new_cart_quantity, 2)
                cart_cache.add_to_cart(callback.from_user.id, item_id, new_cart_quantity)
                await callback.answer(f"Добавлено: +{amount_to_add} {item_data['unit']}")
            else:
                await callback.answer("Достигнуто максимальное доступное количество или товар закончился.", show_alert=True)
                # Не обновляем карточку товара, т.к. ничего не изменилось в корзине или не смогли добавить
                return 
            
        elif action == "decrease":
            item_id, amount_str = params
            item_id_for_update = item_id
            
            item_data = await rq.get_item(item_id) 
            if not item_data:
                await callback.answer("Товар не найден", show_alert=True)
                return

            amount_val: float | int
            if item_data['unit'] == app_config.ITEM_UNIT_ML:
                amount_val = float(amount_str)
            else: 
                amount_val = int(amount_str)

            current_quantity = cart_cache.get_item_quantity(callback.from_user.id, item_id)
            new_quantity = max(0, current_quantity - amount_val)
            if isinstance(new_quantity, float): new_quantity = round(new_quantity, 2)
            
            cart_cache.add_to_cart(callback.from_user.id, item_id, new_quantity)
            await callback.answer(f"Уменьшено до {new_quantity} {item_data['unit']}" if new_quantity > 0 else "Товар убран из корзины")
            
        elif action == "reset": 
            item_id = params[0]
            item_id_for_update = item_id
            cart_cache.remove_from_cart(callback.from_user.id, item_id)
            await callback.answer("Количество сброшено")
            
        elif action == "remove": 
            item_id = params[0]
            cart_cache.remove_from_cart(callback.from_user.id, item_id)
            await cart_handler(callback) 
            await callback.answer("Товар удален из корзины")
            return 
            
        elif action == "clear":
            cart_cache.clear_cart(callback.from_user.id)
            # Проверяем, есть ли у сообщения фото, чтобы не пытаться редактировать текст у фото-сообщения
            if callback.message and callback.message.photo:
                await callback.message.delete()
                await callback.message.answer("Корзина очищена.", reply_markup=menu_keyboard)
            elif callback.message:
                 await callback.message.edit_text("Корзина очищена.", reply_markup=menu_keyboard)
            else: # Если callback.message None (маловероятно, но для безопасности)
                bot_instance = callback.bot # Получаем экземпляр бота из callback
                await bot_instance.send_message(callback.from_user.id, "Корзина очищена.", reply_markup=menu_keyboard)

            await callback.answer("Корзина очищена")
            return
        
        # Обновляем сообщение с карточкой товара, если действие было над ней
        if item_id_for_update:
            item_data = await rq.get_item(item_id_for_update)
            if item_data:
                status_emoji = "🔒" if item_data['status'] == app_config.ITEM_STATUS_RESERVED else "✅"
                status_text = "Забронирован" if item_data['status'] == app_config.ITEM_STATUS_RESERVED else "Доступен"
                quantity_text = f"\n<b>В наличии:</b> {item_data['quantity']} {item_data['unit']}" if item_data['quantity'] > 0 else "\n<b>В наличии:</b> Нет"
                
                price_str = f"{item_data['price']:.2f} руб." if isinstance(item_data.get('price'), (int, float)) else "Цена не указана"
                text = (f"<b>{item_data.get('name', 'Без названия')}</b>\n\n"
                        f"{item_data.get('description', 'Описание отсутствует.')}\n\n"
                        f"<b>Цена:</b> {price_str}\n"
                        f"<b>Статус:</b> {status_emoji} {status_text}"
                        f"{quantity_text}")
                
                cart_quantity = cart_cache.get_item_quantity(callback.from_user.id, item_id_for_update)
                if cart_quantity > 0:
                    text += f"\n\n<b>В корзине:</b> {cart_quantity} {item_data['unit']}"
                
                # Восстанавливаем source_type и source_details, если они были в исходной клавиатуре товара
                source_type: Optional[str] = None
                source_details: dict = {}
                if callback.message and callback.message.reply_markup:
                    # Пытаемся извлечь из кнопки "назад" в текущей клавиатуре
                    # Это сложная и не очень надежная логика.
                    # Проще передавать source_type и source_details в callback_data кнопок корзины,
                    # но это сильно усложнит callback_data.
                    # Пока оставим как есть, кнопка "назад" будет вести на категорию по умолчанию.
                    # Если исходная карточка товара была из поиска, то эта информация теряется при обновлении через cart_action.
                    # Для исправления этого, get_item_cart_keyboard должна также принимать source_type/details и
                    # кнопки +/-/сбросить должны их включать в свой callback_data.
                    pass # Оставляем эту логику пока простой

                reply_markup = get_item_cart_keyboard(
                    item_id_for_update, 
                    callback.from_user.id, 
                    item_data,
                    source_type=source_type, # Будет None, если не смогли извлечь
                    source_details=source_details
                )

                # Логика обновления сообщения (аналогично item_handler)
                if callback.message: # Проверяем, что callback.message существует
                    if item_data.get('image_url'):
                        if callback.message.photo: # Если текущее сообщение уже с фото
                            try:
                                await callback.message.edit_caption(caption=text, reply_markup=reply_markup, parse_mode="HTML")
                            except Exception as e_caption:
                                logger.warning(f"Failed to edit caption, attempting delete and send: {e_caption}")
                                await callback.message.delete()
                                await callback.message.answer_photo(
                                    photo=item_data['image_url'], caption=text, reply_markup=reply_markup, parse_mode="HTML"
                                )
                        else: # Текущее сообщение текстовое, а нужно с фото
                            await callback.message.delete()
                            await callback.message.answer_photo(
                                photo=item_data['image_url'], caption=text, reply_markup=reply_markup, parse_mode="HTML"
                            )
                    else: # Новый контент - текстовый
                        if callback.message.photo: # Текущее сообщение с фото, а нужно текстовое
                            await callback.message.delete()
                            await callback.message.answer(text, reply_markup=reply_markup, parse_mode="HTML")
                        else: # Текущее сообщение текстовое, и новое текстовое
                            try:
                                await callback.message.edit_text(text, reply_markup=reply_markup, parse_mode="HTML")
                            except Exception as e_text:
                                logger.warning(f"Failed to edit text, attempting delete and send: {e_text}")
                                await callback.message.delete()
                                await callback.message.answer(text, reply_markup=reply_markup, parse_mode="HTML")
                else: # callback.message is None - очень маловероятно
                     logger.error("callback.message is None in cart_action_handler during update.")


        # Если мы не ответили ранее с show_alert=True или не вышли из функции
        # Убедимся, что на callback.answer() уже был вызван, если мы не попали в ветки с return
        # В большинстве веток callback.answer уже есть. Если нет, то здесь:
        # await callback.answer() # Закомментировано, т.к. в большинстве случаев уже есть

    except Exception as e:
        logger.error(f"Error in cart_action_handler: {e}", exc_info=True)
        await callback.answer("Произошла ошибка при обработке действия с корзиной", show_alert=True)
def is_admin(user_id: int) -> bool:
    return user_id in app_config.ADMIN_IDS

@router.message(Command("admin"))
async def admin_command(message: Message):
    if not is_admin(message.from_user.id):
        # Можно ничего не отвечать или ответить, что команда не найдена
        return 
    
    await message.answer(
        "Панель администратора",
        reply_markup=get_admin_keyboard()
    )

@router.callback_query(F.data.startswith("admin:")) # Без lambda для простоты
async def process_admin_callback(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("У вас нет доступа к этой функции.", show_alert=True)
        return
    
    action = callback.data.split(":")[1]
    
    if action == "stats":
        await callback.message.edit_text(
            "📊 Статистика\n\nФункция в разработке...",
            reply_markup=get_admin_keyboard() # Возврат к админ-клавиатуре
        )
    elif action == "sync":
        # Здесь можно вызвать функции синхронизации кэша вручную
        try:
            await sync_privacy_cache()
            await sync_catalog_cache()
            await callback.message.edit_text(
                "🔄 Кэши успешно синхронизированы!",
                reply_markup=get_admin_keyboard()
            )
            await callback.answer("Синхронизация завершена.")
        except Exception as e:
            logger.error(f"Admin manual sync error: {e}", exc_info=True)
            await callback.message.edit_text(
                "🔄 Ошибка во время синхронизации.",
                reply_markup=get_admin_keyboard()
            )
            await callback.answer("Ошибка синхронизации.", show_alert=True)
    
    # await callback.answer() # Уже вызван в успешных случаях или при ошибке