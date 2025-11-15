"""
Модуль для работы с базой данных пользователей
"""
import aiosqlite
import os
from typing import Optional, Dict
from datetime import datetime


class Database:
    def __init__(self, db_path: str = "edulingo.db"):
        self.db_path = db_path
    
    async def init_db(self):
        """Инициализация базы данных и создание таблицы"""
        async with aiosqlite.connect(self.db_path) as db:
            # Базовое создание таблицы (для новых БД)
            await db.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    telegram_id INTEGER PRIMARY KEY,
                    username TEXT,
                    language TEXT,
                    first_name TEXT,
                    last_name TEXT,
                    phone TEXT,
                    class INTEGER,
                    school_number TEXT,
                    english_level TEXT,
                    russian_level TEXT,
                    address TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)
            await db.commit()

            # Гарантируем наличие всех нужных колонок для уже существующих БД
            async with db.execute("PRAGMA table_info(users)") as cursor:
                columns_info = await cursor.fetchall()
            existing_columns = {col[1] for col in columns_info}

            columns_to_add = [
                ("username", "TEXT"),
                ("class", "INTEGER"),
                ("school_number", "TEXT"),
                ("english_level", "TEXT"),
                ("russian_level", "TEXT"),
            ]

            for column_name, column_type in columns_to_add:
                if column_name not in existing_columns:
                    try:
                        await db.execute(f"ALTER TABLE users ADD COLUMN {column_name} {column_type}")
                        await db.commit()
                    except aiosqlite.OperationalError:
                        # Колонка уже существует или не может быть добавлена
                        pass
    
    async def get_user(self, telegram_id: int) -> Optional[Dict]:
        """Получить пользователя по telegram_id"""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM users WHERE telegram_id = ?",
                (telegram_id,)
            ) as cursor:
                row = await cursor.fetchone()
                if row:
                    return dict(row)
                return None
    
    async def create_user(self, user_data: Dict) -> bool:
        """Создать нового пользователя"""
        async with aiosqlite.connect(self.db_path) as db:
            try:
                await db.execute("""
                    INSERT INTO users 
                    (telegram_id, username, language, first_name, last_name, phone, class, school_number, english_level, russian_level, address)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    user_data['telegram_id'],
                    user_data.get('username'),
                    user_data.get('language'),
                    user_data.get('first_name'),
                    user_data.get('last_name'),
                    user_data.get('phone'),
                    user_data.get('class'),
                    user_data.get('school_number'),
                    user_data.get('english_level'),
                    user_data.get('russian_level'),
                    user_data.get('address')
                ))
                await db.commit()
                return True
            except aiosqlite.IntegrityError:
                # Пользователь уже существует
                return False
    
    async def update_user(self, telegram_id: int, user_data: Dict) -> bool:
        """Обновить данные пользователя"""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                UPDATE users 
                SET language = ?, first_name = ?, last_name = ?, phone = ?, class = ?, school_number = ?, english_level = ?, russian_level = ?, address = ?
                WHERE telegram_id = ?
            """, (
                user_data.get('language'),
                user_data.get('first_name'),
                user_data.get('last_name'),
                user_data.get('phone'),
                user_data.get('class'),
                user_data.get('school_number'),
                user_data.get('english_level'),
                user_data.get('russian_level'),
                user_data.get('address'),
                telegram_id
            ))
            await db.commit()
            return True
    
    async def user_exists(self, telegram_id: int) -> bool:
        """Проверить существование пользователя"""
        user = await self.get_user(telegram_id)
        return user is not None

