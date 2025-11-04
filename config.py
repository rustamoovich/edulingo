"""
Конфигурационный модуль
"""
import os
from dotenv import load_dotenv

# Загрузка переменных окружения
load_dotenv()

# Настройки бота
BOT_TOKEN = os.getenv("BOT_TOKEN")
BOOK_WEBSITE_URL = os.getenv("BOOK_WEBSITE_URL", "https://edulingo.example.com")
DATABASE_PATH = os.getenv("DATABASE_PATH", "edulingo.db")

# Настройки админ-панели
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin123")
SECRET_KEY = os.getenv("SECRET_KEY", "change_me_secret")

# Проверка обязательных переменных
if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN не установлен! Проверьте файл .env")

