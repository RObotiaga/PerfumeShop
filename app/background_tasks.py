# app/background_tasks.py
import asyncio
import logging
from typing import Optional
from datetime import datetime, timedelta

from app.database.requests import sync_privacy_cache, sync_catalog_cache
from app.database.cache import privacy_cache, catalog_cache

logger = logging.getLogger(__name__)

class BackgroundTasks:
    def __init__(self):
        self._privacy_sync_task: Optional[asyncio.Task] = None
        self._catalog_sync_task: Optional[asyncio.Task] = None
        self._is_running = False
        self._last_privacy_sync = datetime.min
        self._last_catalog_sync = datetime.min
        self._sync_interval = timedelta(minutes=5)

    async def start(self):
        """Запускает все фоновые задачи."""
        if self._is_running:
            logger.warning("Background tasks are already running")
            return

        self._is_running = True
        self._privacy_sync_task = asyncio.create_task(self._sync_privacy_periodically())
        self._catalog_sync_task = asyncio.create_task(self._sync_catalog_periodically())
        logger.info("Background tasks started")

    async def stop(self):
        """Останавливает все фоновые задачи."""
        if not self._is_running:
            return

        self._is_running = False
        
        if self._privacy_sync_task:
            self._privacy_sync_task.cancel()
            try:
                await self._privacy_sync_task
            except asyncio.CancelledError:
                pass
        
        if self._catalog_sync_task:
            self._catalog_sync_task.cancel()
            try:
                await self._catalog_sync_task
            except asyncio.CancelledError:
                pass
        
        logger.info("Background tasks stopped")

    async def _sync_privacy_periodically(self):
        """Периодически синхронизирует кеш конфиденциальности."""
        while self._is_running:
            try:
                current_time = datetime.now()
                if current_time - self._last_privacy_sync >= self._sync_interval:
                    await sync_privacy_cache()
                    self._last_privacy_sync = current_time
                    logger.info("Privacy cache synchronized successfully")
            except Exception as e:
                logger.error(f"Error synchronizing privacy cache: {e}", exc_info=True)
            
            # Ждем 1 минуту перед следующей проверкой
            await asyncio.sleep(60)

    async def _sync_catalog_periodically(self):
        """Периодически синхронизирует кеш каталога."""
        while self._is_running:
            try:
                current_time = datetime.now()
                if current_time - self._last_catalog_sync >= self._sync_interval:
                    await sync_catalog_cache()
                    self._last_catalog_sync = current_time
                    logger.info("Catalog cache synchronized successfully")
            except Exception as e:
                logger.error(f"Error synchronizing catalog cache: {e}", exc_info=True)
            
            # Ждем 1 минуту перед следующей проверкой
            await asyncio.sleep(60)

# Создаем глобальный экземпляр для управления фоновыми задачами
background_tasks = BackgroundTasks() 