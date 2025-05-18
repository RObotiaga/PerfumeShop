# app/database/cache.py
from typing import Dict, Set, List, Optional
import logging
import time
from collections import defaultdict

logger = logging.getLogger(__name__)

class PrivacyCache:
    def __init__(self):
        self._accepted_users: Set[int] = set()
        self._initialized = False
        self._last_update = 0
        self._update_interval = 300  # 5 минут

    def initialize(self, accepted_users: Set[int]) -> None:
        """Инициализирует кэш списком пользователей, согласившихся с политикой."""
        self._accepted_users = accepted_users
        self._initialized = True
        self._last_update = time.time()
        logger.info(f"Privacy cache initialized with {len(accepted_users)} users")

    def is_initialized(self) -> bool:
        """Проверяет, был ли кэш инициализирован."""
        return self._initialized

    def needs_update(self) -> bool:
        return not self._initialized or (time.time() - self._last_update) > self._update_interval

    def is_accepted(self, user_id: int) -> bool:
        """Проверяет, согласился ли пользователь с политикой."""
        return user_id in self._accepted_users

    def add_user(self, user_id: int) -> None:
        """Добавляет пользователя в список согласившихся."""
        self._accepted_users.add(user_id)
        logger.info(f"User {user_id} added to privacy cache")

    def remove_user(self, user_id: int) -> None:
        """Удаляет пользователя из списка согласившихся."""
        self._accepted_users.discard(user_id)
        logger.info(f"User {user_id} removed from privacy cache")

    def get_all_accepted_users(self) -> Set[int]:
        """Возвращает множество всех пользователей, согласившихся с политикой."""
        return self._accepted_users.copy()

class CatalogCache:
    def __init__(self):
        self._categories: List[Dict] = []
        self._items_by_category: Dict[str, List[Dict]] = {}
        self._items_by_id: Dict[str, Dict] = {}
        self._initialized = False
        self._last_update = 0
        self._update_interval = 300  # 5 минут

    def initialize(self, categories: List[Dict], items_by_category: Dict[str, List[Dict]]) -> None:
        """Инициализирует кэш категорий и товаров."""
        self._categories = categories
        self._items_by_category = items_by_category
        self._items_by_id = {}
        for items in items_by_category.values():
            for item in items:
                self._items_by_id[item['id']] = item
        self._initialized = True
        self._last_update = time.time()
        logger.info(f"Catalog cache initialized with {len(categories)} categories and {len(self._items_by_id)} items")

    def is_initialized(self) -> bool:
        """Проверяет, был ли кэш инициализирован."""
        return self._initialized

    def needs_update(self) -> bool:
        """Проверяет, нужно ли обновить кэш."""
        return not self._initialized or (time.time() - self._last_update) > self._update_interval

    def get_categories(self) -> List[Dict]:
        """Возвращает список категорий."""
        return self._categories

    def get_items_by_category(self, category_name: str) -> List[Dict]:
        """Возвращает список товаров для указанной категории."""
        return self._items_by_category.get(category_name, [])

    def get_item(self, item_id: str) -> Optional[Dict]:
        """Находит товар по ID во всех категориях."""
        return self._items_by_id.get(item_id)

    def update(self, categories: List[Dict], items_by_category: Dict[str, List[Dict]]) -> None:
        """Обновляет кэш новыми данными."""
        self._categories = categories
        self._items_by_category = items_by_category
        self._items_by_id = {}
        for items in items_by_category.values():
            for item in items:
                self._items_by_id[item['id']] = item
        self._initialized = True
        self._last_update = time.time()
        logger.info(f"Catalog cache updated with {len(categories)} categories and {len(self._items_by_id)} items")

class CartCache:
    def __init__(self):
        # user_id -> {item_id -> quantity}
        self._carts: Dict[int, Dict[str, int]] = defaultdict(dict)
        self._last_update = 0
        self._update_interval = 3600  # 1 час

    def add_to_cart(self, user_id: int, item_id: str, quantity: int) -> None:
        """Добавляет товар в корзину пользователя."""
        if quantity <= 0:
            self.remove_from_cart(user_id, item_id)
            return
        
        self._carts[user_id][item_id] = quantity
        logger.info(f"Added {quantity} of item {item_id} to cart for user {user_id}")

    def remove_from_cart(self, user_id: int, item_id: str) -> None:
        """Удаляет товар из корзины пользователя."""
        if item_id in self._carts[user_id]:
            del self._carts[user_id][item_id]
            logger.info(f"Removed item {item_id} from cart for user {user_id}")

    def get_cart(self, user_id: int) -> Dict[str, int]:
        """Возвращает корзину пользователя."""
        return self._carts[user_id]

    def clear_cart(self, user_id: int) -> None:
        """Очищает корзину пользователя."""
        self._carts[user_id].clear()
        logger.info(f"Cleared cart for user {user_id}")

    def get_item_quantity(self, user_id: int, item_id: str) -> int:
        """Возвращает количество товара в корзине пользователя."""
        return self._carts[user_id].get(item_id, 0)

    def needs_update(self) -> bool:
        """Проверяет, нужно ли обновить кэш."""
        return (time.time() - self._last_update) > self._update_interval

# Создаем глобальные экземпляры кэшей
privacy_cache = PrivacyCache()
catalog_cache = CatalogCache()
cart_cache = CartCache() 