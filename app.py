from flask import Flask, render_template, request, redirect, url_for, session, send_file, flash
import sqlite3
import io
from datetime import datetime
from openpyxl import Workbook
from openpyxl.styles import Font, Alignment
from config import DATABASE_PATH, ADMIN_USERNAME, ADMIN_PASSWORD, SECRET_KEY

app = Flask(__name__)
app.secret_key = SECRET_KEY


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


@app.errorhandler(404)
def not_found(_):
    return redirect(url_for('users'))


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
