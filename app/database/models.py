import os
from sqlalchemy import String, BigInteger, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, DeclarativeBase
from sqlalchemy.ext.asyncio import AsyncAttrs, async_sessionmaker, create_async_engine

# Получаем URL базы данных из переменных окружения
DB_URL = os.getenv('DB_URL')
if not DB_URL:
    print("Ошибка: URL базы данных DB_URL не найден в .env файле.")
    # Можно здесь завершить выполнение, если DB_URL критичен для запуска
    # exit() # Раскомментировать, если нужно остановить выполнение
else:
    # Создаем асинхронный движок для работы с БД
    engine = create_async_engine(DB_URL, echo=True)

# Создаем фабрику асинхронных сессий
async_session = async_sessionmaker(engine)

# Базовый класс для моделей SQLAlchemy
class Base(AsyncAttrs, DeclarativeBase):
    pass

# Модель пользователя
class User(Base):
    __tablename__ = 'users'

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    tg_id: Mapped[int] = mapped_column(BigInteger) # Используем BigInteger для Telegram ID

# Модель категории товаров
class Category(Base):
    __tablename__ = 'categories'

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(25)) # Ограничиваем длину названия категории

# Модель товара
class Item(Base):
    __tablename__ = 'items'

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    category: Mapped[int] = mapped_column(ForeignKey('categories.id')) # Внешний ключ на таблицу категорий
    name: Mapped[str] = mapped_column(String(128)) # Ограничиваем длину названия товара
    description: Mapped[str] = mapped_column(String(2048), nullable=True) # Ограничиваем длину описания
    price: Mapped[int] = mapped_column()
    image_url: Mapped[str] = mapped_column(String(2048), nullable=True) # URL изображения товара

# Асинхронная функция для создания таблиц в БД
async def async_main():
    async with engine.begin() as conn:
        # Удаляем все таблицы (для отладки, можно закомментировать)
        # await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)