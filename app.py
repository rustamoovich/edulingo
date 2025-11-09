from flask import Flask, render_template, request, redirect, url_for, session, send_file, flash, Response, jsonify
import sqlite3
import io
import os
import logging
import asyncio
from datetime import datetime
from openpyxl import Workbook
from openpyxl.styles import Font, Alignment
from telegram import Update
from config import DATABASE_PATH, ADMIN_USERNAME, ADMIN_PASSWORD, SECRET_KEY
from bot import get_bot_application

app = Flask(__name__)
app.secret_key = SECRET_KEY

# Настройка логирования
logging.basicConfig(level=logging.INFO)

# Инициализация базы данных при запуске Flask
def init_database():
    """Инициализировать базу данных синхронно для Flask"""
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()
    
    # Создаем таблицу users если её нет
    cursor.execute("""
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
    
    # Проверяем наличие колонки username, если нет - добавляем
    cursor.execute("PRAGMA table_info(users)")
    columns = [column[1] for column in cursor.fetchall()]
    if 'username' not in columns:
        try:
            cursor.execute("ALTER TABLE users ADD COLUMN username TEXT")
        except sqlite3.OperationalError:
            pass  # Колонка уже существует
    
    conn.commit()
    conn.close()
    logging.info("База данных инициализирована для Flask")

# Инициализируем базу данных при импорте модуля
init_database()

# Инициализация бота (ленивая)
bot_application = None
_bot_initialized = False

def get_bot():
    """Получить или инициализировать бота (ленивая инициализация)"""
    global bot_application, _bot_initialized
    
    if not _bot_initialized:
        bot_application = get_bot_application()
        
        # Автоматическое определение URL для webhook
        webhook_url = os.environ.get('WEBHOOK_URL')
        
        # Если WEBHOOK_URL не указан, пытаемся определить автоматически
        if not webhook_url:
            # Render.com предоставляет RENDER_EXTERNAL_URL
            render_url = os.environ.get('RENDER_EXTERNAL_URL')
            if render_url:
                webhook_url = render_url
            else:
                # Попытка определить из других источников
                # Можно использовать переменную PORT для определения, что мы на Render/Heroku
                port = os.environ.get('PORT')
                if port:
                    # На Render/Heroku обычно есть переменная с URL
                    # Если нет, можно попробовать определить из запроса
                    pass
        
        # Установка webhook при первой инициализации
        if webhook_url:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                webhook_full_url = f"{webhook_url}/webhook" if not webhook_url.endswith('/webhook') else webhook_url
                loop.run_until_complete(bot_application.bot.set_webhook(url=webhook_full_url))
                logging.info(f"Webhook автоматически установлен: {webhook_full_url}")
            except Exception as e:
                logging.error(f"Ошибка установки webhook: {e}")
            finally:
                loop.close()
        else:
            logging.warning("WEBHOOK_URL не указан и не может быть определен автоматически. Webhook не установлен.")
        
        _bot_initialized = True
    
    return bot_application


def get_db_connection():
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def is_logged_in():
    return session.get('logged_in') is True


def login_required(view_func):
    def wrapper(*args, **kwargs):
        if not is_logged_in():
            return redirect(url_for('login', next=request.path))
        return view_func(*args, **kwargs)
    wrapper.__name__ = view_func.__name__
    return wrapper


@app.route('/admin/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username', '')
        password = request.form.get('password', '')
        if username == ADMIN_USERNAME and password == ADMIN_PASSWORD:
            session['logged_in'] = True
            flash('Добро пожаловать!', 'success')
            next_url = request.args.get('next') or url_for('users')
            return redirect(next_url)
        flash('Неверные данные для входа', 'danger')
    return render_template('login.html')


@app.route('/admin/logout')
@login_required
def logout():
    session.clear()
    flash('Вы вышли из системы', 'info')
    return redirect(url_for('login'))


@app.route('/admin/users')
@login_required
def users():
    q = request.args.get('q', '').strip()
    language = request.args.get('language', '').strip()
    region = request.args.get('region', '').strip()
    page = max(int(request.args.get('page', 1)), 1)
    page_size = min(max(int(request.args.get('page_size', 20)), 5), 100)

    offset = (page - 1) * page_size

    # Загружаем все записи и фильтруем в Python с учётом Unicode-регистра
    conn = get_db_connection()
    rows = conn.execute(
        'SELECT * FROM users ORDER BY datetime(created_at) DESC'
    ).fetchall()
    conn.close()

    def norm(val: str) -> str:
        return (val or '').casefold()

    cq = norm(q)
    clang = norm(language)
    creg = norm(region)

    filtered = []
    for r in rows:
        if language and norm(r['language']) != clang:
            continue
        if region and creg not in norm(r['address']):
            continue
        if q:
            haystacks = [
                norm(r['first_name']),
                norm(r['last_name']),
                norm(r['phone']),
                norm(r['address']),
                norm(r['username']),
                str(r['telegram_id'])
            ]
            if not any(cq in h for h in haystacks):
                continue
        filtered.append(r)

    total = len(filtered)
    paged = filtered[offset:offset + page_size]

    languages = ['ru', 'en', 'uz']

    return render_template(
        'users.html',
        users=paged,
        page=page,
        page_size=page_size,
        total=total,
        q=q,
        language=language,
        region=region,
        languages=languages
    )


@app.route('/admin/users/export')
@login_required
def export_users():
    q = request.args.get('q', '').strip()
    language = request.args.get('language', '').strip()
    region = request.args.get('region', '').strip()

    conn = get_db_connection()
    rows = conn.execute(
        'SELECT telegram_id, username, language, first_name, last_name, phone, address, created_at FROM users ORDER BY datetime(created_at) DESC'
    ).fetchall()
    conn.close()

    def norm(val: str) -> str:
        return (val or '').casefold()

    cq = norm(q)
    clang = norm(language)
    creg = norm(region)

    filtered = []
    for r in rows:
        if language and norm(r['language']) != clang:
            continue
        if region and creg not in norm(r['address']):
            continue
        if q:
            haystacks = [
                norm(r['first_name']),
                norm(r['last_name']),
                norm(r['phone']),
                norm(r['address']),
                norm(r['username']),
                str(r['telegram_id'])
            ]
            if not any(cq in h for h in haystacks):
                continue
        filtered.append(r)

    # Создаем Excel файл
    wb = Workbook()
    ws = wb.active
    ws.title = "Пользователи"
    
    # Заголовки на русском языке
    headers = ['№', 'ID Telegram', 'Username', 'Язык', 'Имя', 'Фамилия', 'Телефон', 'Адрес', 'Дата регистрации']
    ws.append(headers)
    
    # Форматируем заголовки (жирный шрифт, выравнивание по центру, перенос текста)
    center_alignment = Alignment(horizontal='center', vertical='center', wrap_text=True)
    for cell in ws[1]:
        cell.font = Font(bold=True)
        cell.alignment = center_alignment
    
    # Экспортируем данные с нумерацией
    for idx, r in enumerate(filtered, start=1):
        # Форматируем телефон как текст для корректного отображения
        phone = r['phone'] or ''
        
        ws.append([
            idx,  # Номер строки
            r['telegram_id'],
            r['username'] or '',
            r['language'] or '',
            r['first_name'] or '',
            r['last_name'] or '',
            phone,  # openpyxl автоматически обрабатывает текст
            r['address'] or '',
            r['created_at'] or ''
        ])
        
        # Устанавливаем формат телефона как текст
        if phone:
            phone_cell = ws.cell(row=idx + 1, column=7)
            phone_cell.number_format = '@'  # Текстовый формат
        
        # Выравнивание: все вертикально по центру
        # Горизонтально по центру все, кроме столбцов 5, 6 и 8 (имя, фамилия и адрес)
        wrap_alignment_left = Alignment(horizontal='left', vertical='center', wrap_text=True)
        wrap_alignment_center = Alignment(horizontal='center', vertical='center', wrap_text=True)
        
        for col_num in range(1, 10):  # Все столбцы от 1 до 9
            cell = ws.cell(row=idx + 1, column=col_num)
            if col_num == 5 or col_num == 6 or col_num == 8:  # Столбцы Имя, Фамилия и Адрес - по левому краю
                cell.alignment = wrap_alignment_left
            else:  # Остальные столбцы - по центру
                cell.alignment = wrap_alignment_center
    
    # Устанавливаем ширину столбцов
    # Столбец 1 (№) - 7, столбец 4 (Язык) - 7, столбец 8 (Адрес) - 30, остальные - 20
    column_widths = {
        1: 7,   # №
        2: 20,  # ID Telegram
        3: 20,  # Username
        4: 7,   # Язык
        5: 20,  # Имя
        6: 20,  # Фамилия
        7: 20,  # Телефон
        8: 30,  # Адрес
        9: 20   # Дата регистрации
    }
    
    for col_num, width in column_widths.items():
        ws.column_dimensions[ws.cell(row=1, column=col_num).column_letter].width = width
    
    # Сохраняем в память
    mem = io.BytesIO()
    wb.save(mem)
    mem.seek(0)
    
    filename = f'users_{datetime.now().strftime("%Y%m%d_%H%M%S")}.xlsx'
    return send_file(mem, as_attachment=True, download_name=filename, mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')


@app.route('/admin/users/<int:telegram_id>/delete', methods=['POST'])
@login_required
def delete_user(telegram_id: int):
    conn = get_db_connection()
    conn.execute('DELETE FROM users WHERE telegram_id = ?', (telegram_id,))
    conn.commit()
    conn.close()
    flash('Пользователь удалён', 'success')
    return redirect(url_for('users'))


@app.route('/webhook', methods=['POST'])
def webhook():
    """Endpoint для получения обновлений от Telegram"""
    try:
        bot_app = get_bot()
        update = Update.de_json(request.get_json(force=True), bot_app.bot)
        
        # Обработка обновления асинхронно
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(bot_app.process_update(update))
        except Exception as e:
            logging.error(f"Ошибка обработки обновления: {e}")
        finally:
            loop.close()
        
        return Response('ok', status=200)
    except Exception as e:
        logging.error(f"Ошибка в webhook: {e}", exc_info=True)
        return Response('Error', status=500)


@app.route('/webhook/status', methods=['GET'])
def webhook_status():
    """Проверка статуса webhook"""
    try:
        bot_app = get_bot()
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            webhook_info = loop.run_until_complete(bot_app.bot.get_webhook_info())
            
            # Если webhook не установлен, пытаемся установить
            if not webhook_info.url:
                webhook_url = os.environ.get('WEBHOOK_URL') or os.environ.get('RENDER_EXTERNAL_URL')
                if webhook_url:
                    webhook_full_url = f"{webhook_url}/webhook" if not webhook_url.endswith('/webhook') else webhook_url
                    loop.run_until_complete(bot_app.bot.set_webhook(url=webhook_full_url))
                    logging.info(f"Webhook установлен через /webhook/status: {webhook_full_url}")
                    webhook_info = loop.run_until_complete(bot_app.bot.get_webhook_info())
            
            loop.close()
            
            return jsonify({
                'status': 'ok',
                'webhook_url': webhook_info.url,
                'has_custom_certificate': webhook_info.has_custom_certificate,
                'pending_update_count': webhook_info.pending_update_count,
                'last_error_date': str(webhook_info.last_error_date) if webhook_info.last_error_date else None,
                'last_error_message': webhook_info.last_error_message,
                'max_connections': webhook_info.max_connections,
                'allowed_updates': webhook_info.allowed_updates
            })
        except Exception as e:
            loop.close()
            return jsonify({'status': 'error', 'message': str(e)}), 500
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500


@app.route('/')
def index():
    """Главная страница - редирект на админ-панель"""
    return redirect(url_for('users'))


@app.errorhandler(404)
def not_found(e):
    """Обработчик 404 - редирект на админ-панель, но не для webhook endpoints"""
    # Не редиректим webhook endpoints
    if request.path.startswith('/webhook'):
        return jsonify({'error': 'Not found'}), 404
    return redirect(url_for('users'))


if __name__ == '__main__':
    import os
    port = int(os.environ.get('PORT', 5000))
    debug = os.environ.get('FLASK_ENV') != 'production'
    app.run(host='0.0.0.0', port=port, debug=debug)
