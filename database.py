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
            await db.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    telegram_id INTEGER PRIMARY KEY,
                    username TEXT,
                    language TEXT,
                    first_name TEXT,
                    last_name TEXT,
                    phone TEXT,
                    address TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)
            await db.commit()
            
            # Добавляем поле username если его нет (для существующих БД)
            try:
                await db.execute("ALTER TABLE users ADD COLUMN username TEXT")
                await db.commit()
            except aiosqlite.OperationalError:
                # Колонка уже существует
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
                    (telegram_id, username, language, first_name, last_name, phone, address)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (
                    user_data['telegram_id'],
                    user_data.get('username'),
                    user_data.get('language'),
                    user_data.get('first_name'),
                    user_data.get('last_name'),
                    user_data.get('phone'),
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
                SET language = ?, first_name = ?, last_name = ?, phone = ?, address = ?
                WHERE telegram_id = ?
            """, (
                user_data.get('language'),
                user_data.get('first_name'),
                user_data.get('last_name'),
                user_data.get('phone'),
                user_data.get('address'),
                telegram_id
            ))
            await db.commit()
            return True
    
    async def user_exists(self, telegram_id: int) -> bool:
        """Проверить существование пользователя"""
        user = await self.get_user(telegram_id)
        return user is not None

