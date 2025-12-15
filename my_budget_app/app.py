import sqlite3
from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify
import datetime
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
import requests
import json
import os
import smtplib
from email.message import EmailMessage

app = Flask(__name__)
app.secret_key = os.environ.get('FLASK_SECRET', 'smart_budget_secret_key_2024')

# === SMTP конфиг (через env vars рекомендуем) ===
EMAIL_HOST = os.environ.get('EMAIL_HOST', 'smtp.gmail.com')
EMAIL_PORT = int(os.environ.get('EMAIL_PORT', 587))
EMAIL_USER = os.environ.get('EMAIL_USER', '')
EMAIL_PASS = os.environ.get('EMAIL_PASS', '')

def get_db_connection():
    conn = sqlite3.connect('database.db', check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db_connection()
    conn.execute('''CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            salary REAL DEFAULT 0,
            rent_expense REAL DEFAULT 0,
            salary_day INTEGER DEFAULT 1,
            rent_day INTEGER DEFAULT 1,
            financial_goal REAL DEFAULT 5000
        )''')
    conn.execute('''CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            type TEXT NOT NULL,
            amount REAL NOT NULL,
            category TEXT NOT NULL,
            date TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users (id)
        )''')
    conn.commit()
    conn.close()

init_db()

# === ensure extra columns exist ===
def ensure_columns():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("PRAGMA table_info(users)")
    cols = [r['name'] for r in cur.fetchall()]
    
    # Добавляем недостающие колонки
    columns_to_add = ['email', 'last_notifications', 'financial_goal']
    for column in columns_to_add:
        if column not in cols:
            try:
                if column == 'financial_goal':
                    conn.execute(f"ALTER TABLE users ADD COLUMN {column} REAL DEFAULT 5000")
                else:
                    conn.execute(f"ALTER TABLE users ADD COLUMN {column} TEXT")
            except Exception as e:
                app.logger.warning(f"Could not add {column} column: {str(e)}")
    
    conn.commit()
    conn.close()

ensure_columns()

# шаблонный фильтр
@app.template_filter('min')
def min_filter(value, limit):
    return min(value, limit)

# Получение курсов валют
def get_currency_rates():
    try:
        response = requests.get('https://api.exchangerate-api.com/v4/latest/USD', timeout=5)
        data = response.json()
        return {
            'USD': 1,
            'EUR': data['rates'].get('EUR', 0.93),
            'GBP': data['rates'].get('GBP', 0.79),
            'JPY': data['rates'].get('JPY', 150.25),
            'CNY': data['rates'].get('CNY', 7.18),
            'RUB': data['rates'].get('RUB', 92.50)
        }
    except:
        return {
            'USD': 1,
            'EUR': 0.93,
            'GBP': 0.79,
            'JPY': 150.25,
            'CNY': 7.18,
            'RUB': 92.50
        }

def get_crypto_rates():
    try:
        response = requests.get('https://api.coingecko.com/api/v3/simple/price?ids=bitcoin,ethereum,binancecoin,ripple,cardano&vs_currencies=usd', timeout=5)
        data = response.json()
        return {
            'BTC': data['bitcoin']['usd'],
            'ETH': data['ethereum']['usd'],
            'BNB': data['binancecoin']['usd'],
            'XRP': data['ripple']['usd'],
            'ADA': data['cardano']['usd']
        }
    except:
        return {
            'BTC': 45000,
            'ETH': 2500,
            'BNB': 320,
            'XRP': 0.65,
            'ADA': 0.48
        }

def get_current_balance(user_id):
    conn = get_db_connection()
    today = datetime.now()
    first_day_of_month = today.replace(day=1).strftime("%Y-%m-%d")
    transactions = conn.execute('SELECT type, amount FROM transactions WHERE user_id = ? AND date >= ?', (user_id, first_day_of_month)).fetchall()
    total_income = 0
    total_expenses = 0
    for t in transactions:
        if t['type'] == 'income':
            total_income += t['amount']
        else:
            total_expenses += t['amount']
    conn.close()
    return total_income - total_expenses


def ai_financial_analysis(user_id, total_income, total_expenses, expenses_by_category):
    conn = get_db_connection()
    user = conn.execute('SELECT salary, rent_expense, salary_day, rent_day FROM users WHERE id = ?', (user_id,)).fetchone()
    conn.close()
    salary = user['salary'] if user and user['salary'] else 0
    rent = user['rent_expense'] if user and user['rent_expense'] else 0
    advice = []
    
    # Основные рекомендации (не более 3)
    if expenses_by_category:
        total_spent = sum(expenses_by_category.values())
        if total_spent > 0:
            # Находим самую крупную категорию расходов
            max_category = max(expenses_by_category, key=expenses_by_category.get)
            max_percentage = (expenses_by_category[max_category] / total_spent * 100)
            if max_percentage > 40:
                advice.append(f"⚠️ Больше всего вы тратите на {max_category} ({max_percentage:.1f}%). Подумайте об оптимизации.")
    
    if rent > 0 and total_income > 0:
        rent_percentage = (rent / total_income * 100)
        if rent_percentage > 40:
            advice.append(f"🚨 Аренда составляет {rent_percentage:.1f}% от доходов")
        elif rent_percentage > 30:
            advice.append(f"⚠️ Аренда {rent_percentage:.1f}% от доходов")
    
    if total_income > 0:
        savings_rate = ((total_income - total_expenses) / total_income * 100)
        if savings_rate < 10:
            advice.append(f"💡 Сберегайте больше! Сейчас откладываете {savings_rate:.1f}%")
        else:
            advice.append(f"✅ Отлично! Сберегаете {savings_rate:.1f}% доходов")
    
    # Ограничиваем количество советов
    return advice[:3]

# === EMAIL utilities ===
def send_email(to_email, subject, body):
    if not to_email:
        app.logger.info("No email provided — skipping send.")
        return False
    try:
        msg = EmailMessage()
        msg['From'] = EMAIL_USER
        msg['To'] = to_email
        msg['Subject'] = subject
        msg.set_content(body)

        server = smtplib.SMTP(EMAIL_HOST, EMAIL_PORT, timeout=10)
        server.starttls()
        server.login(EMAIL_USER, EMAIL_PASS)
        server.send_message(msg)
        server.quit()
        app.logger.info(f"Email sent to {to_email}: {subject}")
        return True
    except Exception as e:
        app.logger.error(f"Failed to send email to {to_email}: {e}")
        return False

def load_last_notifications(user_row):
    try:
        if not user_row or not user_row['last_notifications']:
            return {}
        return json.loads(user_row['last_notifications'])
    except Exception:
        return {}

def save_last_notifications(user_id, notifications_dict):
    conn = get_db_connection()
    conn.execute('UPDATE users SET last_notifications = ? WHERE id = ?', (json.dumps(notifications_dict), user_id))
    conn.commit()
    conn.close()

def check_and_send_notifications_for_user(user_id):
    conn = get_db_connection()
    user = conn.execute('SELECT id, email, salary, rent_expense, salary_day, rent_day, last_notifications FROM users WHERE id = ?', (user_id,)).fetchone()
    if not user:
        conn.close()
        return
    today = datetime.now()
    first_day_of_month = today.replace(day=1).strftime("%Y-%m-%d")
    transactions = conn.execute('SELECT type, amount FROM transactions WHERE user_id = ? AND date >= ?', (user_id, first_day_of_month)).fetchall()
    conn.close()
    total_income = 0
    total_expenses = 0
    for t in transactions:
        if t['type'] == 'income':
            total_income += t['amount']
        else:
            total_expenses += t['amount']
    last_notifs = load_last_notifications(user)
    
    # Уведомления (упрощенные)
    try:
        if user['rent_expense'] and user['rent_day']:
            rent_day = min(int(user['rent_day']), 28)
            next_rent = today.replace(day=rent_day)
            if today.day >= rent_day:
                month = next_rent.month + 1
                year = next_rent.year
                if month == 13:
                    month = 1
                    year += 1
                next_rent = next_rent.replace(month=month, year=year)
            days_until_rent = (next_rent - today).days
            if days_until_rent == 3:
                last_date = last_notifs.get('rent', '')
                if last_date != today.strftime('%Y-%m-%d'):
                    subject = "Напоминание: оплата аренды через 3 дня"
                    body = f"Привет! Напоминание: оплата аренды {user['rent_expense']} ₽ назначена через 3 дня ({next_rent.strftime('%Y-%m-%d')})."
                    if send_email(user['email'], subject, body):
                        last_notifs['rent'] = today.strftime('%Y-%m-%d')
                        save_last_notifications(user_id, last_notifs)
    except Exception as e:
        app.logger.error("Rent notification error: " + str(e))

# ИЗМЕНЕНИЕ №1: Корневой маршрут теперь ведет на welcome страницу
@app.route('/')
def root():
    """Корневой маршрут - всегда ведет на приветственную страницу"""
    return redirect(url_for('welcome'))

@app.route('/dashboard')
def index():
    """Главная страница дашборда (только для авторизованных)"""
    if 'user_id' not in session:
        return redirect(url_for('welcome'))
    
    conn = get_db_connection()
    today = datetime.now()
    first_day_of_month = today.replace(day=1).strftime("%Y-%m-%d")
    transactions = conn.execute('SELECT type, amount, category FROM transactions WHERE user_id = ? AND date >= ?', (session['user_id'], first_day_of_month)).fetchall()
    expenses = conn.execute('SELECT category, SUM(amount) as total FROM transactions WHERE user_id = ? AND type = "expense" AND date >= ? GROUP BY category', (session['user_id'], first_day_of_month)).fetchall()
    user = conn.execute('SELECT salary, rent_expense, salary_day, rent_day, email, last_notifications, financial_goal FROM users WHERE id = ?', (session['user_id'],)).fetchone()
    conn.close()
    
    total_income = 0
    total_expenses = 0
    expenses_by_category = {}
    chart_labels = []
    chart_data = []
    
    for t in transactions:
        if t['type'] == 'income':
            total_income += t['amount']
        else:
            total_expenses += t['amount']
            expenses_by_category[t['category']] = expenses_by_category.get(t['category'], 0) + t['amount']
    
    for expense in expenses:
        chart_labels.append(expense['category'])
        chart_data.append(expense['total'])
    
    currency_rates = get_currency_rates()
    crypto_rates = get_crypto_rates()
    ai_advice = ai_financial_analysis(session['user_id'], total_income, total_expenses, expenses_by_category)
    balance = total_income - total_expenses
    now = datetime.now()
    current_balance = get_current_balance(session['user_id'])
    
    # Получаем цель из базы данных
    financial_goal = user['financial_goal'] if user and user['financial_goal'] else 5000
    if 'financial_goal' not in session:
        session['financial_goal'] = financial_goal
    
    # Проверяем и отправляем email-уведомления
    try:
        check_and_send_notifications_for_user(session['user_id'])
    except Exception as e:
        app.logger.error("Notification check failed: " + str(e))

    return render_template('index.html',
                         total_income=total_income,
                         total_expenses=total_expenses,
                         balance=balance,
                         chart_labels=chart_labels,
                         chart_data=chart_data,
                         now=now,
                         currency_rates=currency_rates,
                         crypto_rates=crypto_rates,
                         ai_advice=ai_advice,
                         user_settings=user)

@app.route('/settings', methods=('GET', 'POST'))
def settings():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    conn = get_db_connection()
    if request.method == 'POST':
        salary = float(request.form.get('salary', 0))
        rent_expense = float(request.form.get('rent_expense', 0))
        salary_day = int(request.form.get('salary_day', 1))
        rent_day = int(request.form.get('rent_day', 1))
        email = request.form.get('email', '').strip() or None
        
        conn.execute('UPDATE users SET salary = ?, rent_expense = ?, salary_day = ?, rent_day = ?, email = ? WHERE id = ?', 
                    (salary, rent_expense, salary_day, rent_day, email, session['user_id']))
        conn.commit()
        flash('Настройки успешно сохранены!', 'success')
    
    user = conn.execute('SELECT salary, rent_expense, salary_day, rent_day, email FROM users WHERE id = ?', (session['user_id'],)).fetchone()
    conn.close()
    return render_template('settings.html', user_settings=user)

@app.route('/update_goal', methods=['POST'])
def update_goal():
    if 'user_id' not in session:
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({'error': 'Not authorized'}), 401
        return redirect(url_for('login'))
    
    new_goal = float(request.form.get('goal_amount', 5000))
    
    # Сохраняем цель в сессии
    session['financial_goal'] = new_goal
    
    # Сохраняем цель в базе данных
    conn = get_db_connection()
    conn.execute('UPDATE users SET financial_goal = ? WHERE id = ?', (new_goal, session['user_id']))
    conn.commit()
    conn.close()
    
    flash('Цель успешно обновлена!', 'success')
    return redirect(url_for('index'))

@app.route('/api/goal')
def get_goal():
    if 'user_id' not in session:
        return jsonify({'error': 'Not authorized'}), 401
    
    conn = get_db_connection()
    user = conn.execute('SELECT financial_goal FROM users WHERE id = ?', (session['user_id'],)).fetchone()
    conn.close()
    
    goal = user['financial_goal'] if user and user['financial_goal'] else 5000
    return jsonify({'goal': goal})

@app.route('/register', methods=('GET', 'POST'))
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        confirm_password = request.form.get('confirm_password', '')
        captcha = request.form.get('captcha', '')
        
        if captcha != '7':
            flash('Неверный ответ капчи! Попробуйте снова.', 'error')
            return render_template('register.html')
        
        if len(password) < 8:
            flash('Пароль должен содержать минимум 8 символов!', 'error')
            return render_template('register.html')
        
        if not any(char.isupper() for char in password):
            flash('Пароль должен содержать хотя бы одну заглавную букву!', 'error')
            return render_template('register.html')
        
        if not any(char.isdigit() for char in password):
            flash('Пароль должен содержать хотя бы одну цифру!', 'error')
            return render_template('register.html')
        
        if password != confirm_password:
            flash('Пароли не совпадают!', 'error')
            return render_template('register.html')
        
        hashed_password = generate_password_hash(password)
        conn = get_db_connection()
        try:
            conn.execute('INSERT INTO users (username, password) VALUES (?, ?)', (username, hashed_password))
            conn.commit()
            flash('Регистрация прошла успешно! Теперь можно войти.', 'success')
            return redirect(url_for('login'))
        except sqlite3.IntegrityError:
            flash('Это имя пользователя уже занято.', 'error')
        finally:
            conn.close()
    
    return render_template('register.html')

@app.route('/login', methods=('GET', 'POST'))
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        captcha = request.form.get('captcha', '')
        
        if captcha != '4':
            flash('Неверный ответ капчи! Попробуйте снова.', 'error')
            return render_template('login.html')
        
        conn = get_db_connection()
        user = conn.execute('SELECT * FROM users WHERE username = ?', (username,)).fetchone()
        conn.close()
        
        if user and check_password_hash(user['password'], password):
            session['user_id'] = user['id']
            session['username'] = user['username']
            
            # Загружаем цель из базы данных
            if user['financial_goal']:
                session['financial_goal'] = user['financial_goal']
            
            return redirect(url_for('index'))
        else:
            flash('Неверное имя пользователя или пароль.', 'error')
    
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('welcome'))  # Изменено: после выхода на welcome

@app.route('/add', methods=('GET', 'POST'))
def add_transaction():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    if request.method == 'POST':
        type = request.form['type']
        amount = float(request.form['amount'])
        category = request.form['category']
        date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        conn = get_db_connection()
        conn.execute('INSERT INTO transactions (user_id, type, amount, category, date) VALUES (?, ?, ?, ?, ?)', 
                    (session['user_id'], type, amount, category, date))
        conn.commit()
        conn.close()
        
        flash('Операция успешно добавлена!', 'success')
        
        # Проверка уведомлений
        try:
            check_and_send_notifications_for_user(session['user_id'])
        except Exception as e:
            app.logger.error("Notification check after add failed: " + str(e))
        
        return redirect(url_for('index'))
    
    return render_template('add.html')

@app.route('/history')
def history():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    conn = get_db_connection()
    transactions = conn.execute('SELECT * FROM transactions WHERE user_id = ? ORDER BY date DESC', (session['user_id'],)).fetchall()
    conn.close()
    return render_template('history.html', transactions=transactions)

@app.route('/welcome')
def welcome():
    """Страница приветствия"""
    if 'user_id' in session:
        return redirect(url_for('index'))
    return render_template('welcome.html')

@app.route('/get_user_stats')
def get_user_stats():
    if 'user_id' not in session:
        return jsonify({'error': 'Not authorized'}), 401
    
    conn = get_db_connection()
    today = datetime.now()
    first_day_of_month = today.replace(day=1).strftime("%Y-%m-%d")
    
    transactions = conn.execute(
        'SELECT type, amount FROM transactions WHERE user_id = ? AND date >= ?',
        (session['user_id'], first_day_of_month)
    ).fetchall()
    
    total_income = sum(t['amount'] for t in transactions if t['type'] == 'income')
    total_expenses = sum(t['amount'] for t in transactions if t['type'] == 'expense')
    balance = total_income - total_expenses
    
    conn.close()
    
    return jsonify({
        'income': total_income,
        'expenses': total_expenses,
        'balance': balance
    })

# Маршрут для тестирования конфетти
@app.route('/test_confetti')
def test_confetti():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    return render_template('test_confetti.html')

if __name__ == '__main__':
    app.run(debug=True, threaded=True)