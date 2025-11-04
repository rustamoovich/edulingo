"""
Скрипт для просмотра зарегистрированных пользователей
"""
import asyncio
from database import Database
from config import DATABASE_PATH


async def view_users():
    """Показать всех зарегистрированных пользователей"""
    import aiosqlite
    db = Database(DATABASE_PATH)
    
    async with aiosqlite.connect(db.db_path) as conn:
        conn.row_factory = aiosqlite.Row
        async with conn.execute("SELECT * FROM users ORDER BY created_at DESC") as cursor:
            rows = await cursor.fetchall()
            
            if not rows:
                print("Пользователи не найдены.")
                return
            
            print(f"\nВсего зарегистрировано пользователей: {len(rows)}\n")
            print("-" * 100)
            
            for row in rows:
                user = dict(row)
                print(f"ID: {user['telegram_id']}")
                print(f"Язык: {user.get('language', 'не указан')}")
                print(f"Имя: {user.get('first_name', 'не указано')}")
                print(f"Фамилия: {user.get('last_name', 'не указано')}")
                print(f"Телефон: {user.get('phone', 'не указан')}")
                print(f"Адрес: {user.get('address', 'не указан')}")
                print(f"Дата регистрации: {user.get('created_at', 'не указана')}")
                print("-" * 100)


if __name__ == '__main__':
    asyncio.run(view_users())

