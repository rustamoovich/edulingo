from flask import Flask, render_template, request, redirect, url_for, session, send_file, flash
import sqlite3
import io
import csv
from datetime import datetime
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

    where = []
    params = []
    if q:
        where.append('(first_name LIKE ? OR last_name LIKE ? OR phone LIKE ? OR address LIKE ? OR CAST(telegram_id AS TEXT) LIKE ?)')
        like = f'%{q}%'
        params.extend([like, like, like, like, like])
    if language:
        where.append('language = ?')
        params.append(language)
    if region:
        where.append('address LIKE ?')
        params.append(f'%{region}%')

    where_sql = ('WHERE ' + ' AND '.join(where)) if where else ''

    offset = (page - 1) * page_size

    conn = get_db_connection()
    total = conn.execute(f'SELECT COUNT(*) FROM users {where_sql}', params).fetchone()[0]
    rows = conn.execute(
        f'SELECT * FROM users {where_sql} ORDER BY datetime(created_at) DESC LIMIT ? OFFSET ?',
        params + [page_size, offset]
    ).fetchall()
    conn.close()

    languages = ['ru', 'en', 'uz']

    return render_template(
        'users.html',
        users=rows,
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

    where = []
    params = []
    if q:
        where.append('(first_name LIKE ? OR last_name LIKE ? OR phone LIKE ? OR address LIKE ? OR CAST(telegram_id AS TEXT) LIKE ?)')
        like = f'%{q}%'
        params.extend([like, like, like, like, like])
    if language:
        where.append('language = ?')
        params.append(language)
    if region:
        where.append('address LIKE ?')
        params.append(f'%{region}%')
    where_sql = ('WHERE ' + ' AND '.join(where)) if where else ''

    conn = get_db_connection()
    rows = conn.execute(
        f'SELECT telegram_id, language, first_name, last_name, phone, address, created_at FROM users {where_sql} ORDER BY datetime(created_at) DESC',
        params
    ).fetchall()
    conn.close()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['telegram_id', 'language', 'first_name', 'last_name', 'phone', 'address', 'created_at'])
    for r in rows:
        writer.writerow([r['telegram_id'], r['language'], r['first_name'], r['last_name'], r['phone'], r['address'], r['created_at']])

    mem = io.BytesIO()
    mem.write(output.getvalue().encode('utf-8-sig'))
    mem.seek(0)
    filename = f'users_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv'
    return send_file(mem, as_attachment=True, download_name=filename, mimetype='text/csv')


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
