# Edulingo Telegram Bot

Telegram-бот для регистрации пользователей книги Edulingo (англо-русско-узбекский разговорник).

## Описание

При первом сканировании QR-кода на обложке книги пользователь попадает в Telegram-бот, где проходит регистрацию:
1. Выбор языка интерфейса (Русский, English, Oʻzbekcha)
2. Отправка контакта (номер телефона)
3. Ввод имени
4. Ввод фамилии
5. Выбор области Узбекистана
6. Ввод адреса проживания

Все данные сохраняются в базе данных SQLite.

При повторных сканированиях QR-кода бот автоматически распознает зарегистрированного пользователя и перенаправляет его на сайт книги.

## Установка

### 1. Клонирование репозитория
```bash
git clone <repository-url>
cd edulingo
```

### 2. Создание виртуального окружения
```bash
python -m venv venv
```

### Windows:
```bash
venv\Scripts\activate
```

### Linux/Mac:
```bash
source venv/bin/activate
```

### 3. Установка зависимостей
```bash
pip install -r requirements.txt
```

### 4. Настройка переменных окружения

Создайте файл `.env` на основе `.env.example` и укажите:
- `BOT_TOKEN` — токен бота от [@BotFather](https://t.me/BotFather)
- `BOOK_WEBSITE_URL` — URL сайта книги
- `DATABASE_PATH` — путь к базе SQLite
- `ADMIN_USERNAME`, `ADMIN_PASSWORD`, `SECRET_KEY` — доступ к админ-панели

## Настройка QR-кода

QR-код на обложке книги должен содержать ссылку вида:
```
https://t.me/your_bot_username?start=edulingo
```
Замените `your_bot_username` на имя вашего бота (без @).

## Запуск бота

```bash
python bot.py
```

Бот запустится и начнет принимать сообщения. База данных будет создана автоматически при первом запуске.

## Админ-панель (просмотр клиентской базы)

Красивый веб-интерфейс для администратора: поиск, фильтры, пагинация, экспорт CSV, удаление.

Запуск:
```bash
python app.py
```
Затем откройте `http://localhost:5000/admin/login`

Функции:
- Поиск по имени/фамилии/телефону/адресу/ID
- Фильтр по языку и региону (по адресу)
- Пагинация
- Экспорт текущей выборки в CSV
- Удаление пользователя

## Просмотр зарегистрированных пользователей (CLI)

```bash
python view_users.py
```

## Структура проекта

```
edulingo/
├── bot.py               # Основной файл бота
├── app.py               # Flask админ-панель
├── templates/           # HTML-шаблоны админки
│   ├── layout.html
│   ├── login.html
│   └── users.html
├── database.py          # Модуль работы с базой данных
├── config.py            # Конфигурационный модуль
├── view_users.py        # Скрипт для просмотра пользователей в консоли
├── requirements.txt     # Зависимости Python
├── .env.example         # Пример файла конфигурации (создайте .env)
└── README.md            # Документация
```

## База данных

База данных SQLite автоматически создается при первом запуске. Таблица `users` содержит следующие поля:

- `telegram_id` (INTEGER PRIMARY KEY) — ID пользователя
- `language` (TEXT) — Язык интерфейса (ru/en/uz)
- `first_name` (TEXT) — Имя
- `last_name` (TEXT) — Фамилия
- `phone` (TEXT) — Телефон
- `address` (TEXT) — Адрес (включая регион)
- `created_at` (TEXT) — Дата регистрации

## Деплой на Heroku

### Подготовка

1. Установите [Heroku CLI](https://devcenter.heroku.com/articles/heroku-cli)

2. Войдите в Heroku:
```bash
heroku login
```

3. Создайте приложение на Heroku:
```bash
heroku create your-app-name
```

4. Добавьте переменные окружения в Heroku:
```bash
heroku config:set BOT_TOKEN=your_bot_token
heroku config:set BOOK_WEBSITE_URL=https://your-book-website.com
heroku config:set ADMIN_USERNAME=admin
heroku config:set ADMIN_PASSWORD=your_secure_password
heroku config:set SECRET_KEY=your_secret_key
heroku config:set WEBHOOK_URL=https://your-app-name.herokuapp.com
```

5. Деплой:
```bash
git push heroku main
```

### Структура на Heroku

- **web dyno** — запускает Flask админ-панель и обрабатывает webhook для Telegram-бота (gunicorn)
- Бот работает через webhook, не требуется отдельный worker dyno

### Важные замечания

- Heroku использует эфемерную файловую систему — файлы SQLite будут удаляться при перезапуске dyno
- Рекомендуется использовать PostgreSQL для продакшена (Heroku Postgres)
- Для постоянного хранения данных рассмотрите использование внешней БД или облачного хранилища

## Лицензия

MIT License