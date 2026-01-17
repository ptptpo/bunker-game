from flask import Flask, render_template, request, redirect, url_for, flash, session
import sqlite3
import hashlib
import secrets
import random

app = Flask(__name__)
app.secret_key = 'bunker-key-123'

ROLES = ["👨‍🍳 Повар", "👮 Полицейский", "👨‍🔬 Ученый", "👨‍🔬 Биолог", "👨‍🔬 Физик", "🏃 Спортсмен"]

# ========== БАЗА ДАННЫХ ==========
def init_db():
    """Простая инициализация базы"""
    print("📀 Создаем базу данных...")
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    
    # Удаляем все старые таблицы
    c.execute("DROP TABLE IF EXISTS room_members")
    c.execute("DROP TABLE IF EXISTS rooms")
    c.execute("DROP TABLE IF EXISTS users")
    
    # Создаем таблицы
    c.execute('''CREATE TABLE users (
        id INTEGER PRIMARY KEY,
        username TEXT UNIQUE,
        password TEXT)''')
    
    c.execute('''CREATE TABLE rooms (
        id TEXT PRIMARY KEY,
        name TEXT,
        owner TEXT,
        game_started INTEGER DEFAULT 0)''')  # SQLite использует INTEGER для boolean
    
    c.execute('''CREATE TABLE room_members (
        room_id TEXT,
        username TEXT,
        role TEXT,
        joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (room_id, username))''')
    
    conn.commit()
    conn.close()
    print("✅ База создана!")

def get_db():
    """Простое соединение с базой"""
    conn = sqlite3.connect('users.db')
    return conn

# ========== ХЕЛПЕРЫ ==========
def hash_password(pwd):
    return hashlib.sha256(pwd.encode()).hexdigest()

def gen_room_id():
    return secrets.token_hex(4)

# ========== МАРШРУТЫ ==========
@app.route('/')
def index():
    if 'username' in session:
        username = session['username']
        conn = get_db()
        c = conn.cursor()
        
        # Мои комнаты
        c.execute("SELECT id, name FROM rooms WHERE owner=?", (username,))
        my_rooms = c.fetchall()
        
        # Комнаты где я участник
        c.execute('''SELECT r.id, r.name, r.owner, r.game_started 
                     FROM rooms r, room_members rm 
                     WHERE r.id=rm.room_id AND rm.username=?''', (username,))
        joined_rooms = c.fetchall()
        
        conn.close()
        
        return render_template('index.html',
                               username=username,
                               my_rooms=my_rooms,
                               joined_rooms=joined_rooms,
                               roles=ROLES)
    
    return render_template('index.html', roles=ROLES)

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        confirm = request.form['confirm_password']
        
        if password != confirm:
            flash('Пароли не совпадают!', 'error')
        elif len(username) < 3:
            flash('Имя от 3 символов', 'error')
        elif len(password) < 6:
            flash('Пароль от 6 символов', 'error')
        else:
            hashed = hash_password(password)
            conn = get_db()
            c = conn.cursor()
            
            try:
                c.execute("INSERT INTO users (username, password) VALUES (?,?)", 
                         (username, hashed))
                conn.commit()
                session['username'] = username
                flash('Регистрация успешна!', 'success')
                return redirect('/')
            except:
                flash('Пользователь уже есть', 'error')
            finally:
                conn.close()
    
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        hashed = hash_password(password)
        
        conn = get_db()
        c = conn.cursor()
        c.execute("SELECT * FROM users WHERE username=? AND password=?", 
                 (username, hashed))
        user = c.fetchone()
        conn.close()
        
        if user:
            session['username'] = username
            flash(f'Привет, {username}!', 'success')
            return redirect('/')
        else:
            flash('Неверные данные', 'error')
    
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.pop('username', None)
    flash('Вы вышли', 'info')
    return redirect('/')

@app.route('/create_room', methods=['POST'])
def create_room():
    if 'username' not in session:
        return redirect('/login')
    
    room_name = request.form.get('room_name', 'Новая комната')
    username = session['username']
    room_id = gen_room_id()
    
    conn = get_db()
    c = conn.cursor()
    
    try:
        # Создаем комнату
        c.execute("INSERT INTO rooms (id, name, owner) VALUES (?,?,?)",
                 (room_id, room_name, username))
        # Добавляем создателя
        c.execute("INSERT INTO room_members (room_id, username) VALUES (?,?)",
                 (room_id, username))
        conn.commit()
        flash(f'Комната "{room_name}" создана!', 'success')
    except Exception as e:
        flash(f'Ошибка: {e}', 'error')
    finally:
        conn.close()
    
    return redirect(f'/room/{room_id}')

@app.route('/room/<room_id>')
def room(room_id):
    """ГЛАВНЫЙ ИСПРАВЛЕННЫЙ МЕТОД"""
    if 'username' not in session:
        return redirect('/login')
    
    username = session['username']
    
    try:
        conn = get_db()
        c = conn.cursor()
        
        # 1. Проверяем существует ли комната
        c.execute("SELECT id, name, owner, game_started FROM rooms WHERE id=?", (room_id,))
        room_data = c.fetchone()
        
        if not room_data:
            flash('Комната не найдена!', 'error')
            conn.close()
            return redirect('/')
        
        room_id, room_name, room_owner, game_started = room_data
        
        # 2. Добавляем пользователя если его нет
        c.execute("SELECT 1 FROM room_members WHERE room_id=? AND username=?", 
                 (room_id, username))
        if not c.fetchone():
            c.execute("INSERT INTO room_members (room_id, username) VALUES (?,?)",
                     (room_id, username))
            conn.commit()
        
        # 3. Получаем участников
        c.execute("SELECT username, role FROM room_members WHERE room_id=? ORDER BY joined_at",
                 (room_id,))
        members_data = c.fetchall()
        
        # Преобразуем в список кортежей
        members = []
        for member in members_data:
            members.append((member[0], member[1]))
        
        # 4. Роль текущего пользователя
        c.execute("SELECT role FROM room_members WHERE room_id=? AND username=?",
                 (room_id, username))
        role_result = c.fetchone()
        user_role = role_result[0] if role_result else None
        
        conn.close()
        
        # 5. Ссылка для приглашения
        room_link = f"{request.host_url}join/{room_id}"
        
        # 6. Рендерим страницу
        return render_template('room.html',
                               room_id=room_id,
                               room_name=room_name,
                               room_owner=room_owner,
                               game_started=bool(game_started),
                               members=members,
                               user_role=user_role,
                               room_link=room_link,
                               username=username,
                               roles=ROLES)
        
    except Exception as e:
        print(f"❌ ОШИБКА в room(): {e}")
        flash(f'Ошибка: {str(e)[:100]}', 'error')
        return redirect('/')

@app.route('/join/<room_id>')
def join_room(room_id):
    if 'username' not in session:
        flash('Войдите сначала', 'error')
        return redirect('/login')
    
    username = session['username']
    
    conn = get_db()
    c = conn.cursor()
    
    # Проверяем комнату
    c.execute("SELECT 1 FROM rooms WHERE id=?", (room_id,))
    if not c.fetchone():
        flash('Комнаты нет', 'error')
        conn.close()
        return redirect('/')
    
    # Проверяем участника
    c.execute("SELECT 1 FROM room_members WHERE room_id=? AND username=?", 
             (room_id, username))
    if not c.fetchone():
        c.execute("INSERT INTO room_members (room_id, username) VALUES (?,?)",
                 (room_id, username))
        conn.commit()
        flash('Вы в комнате!', 'success')
    
    conn.close()
    return redirect(f'/room/{room_id}')

@app.route('/start_game/<room_id>')
def start_game(room_id):
    if 'username' not in session:
        return redirect('/login')
    
    username = session['username']
    
    conn = get_db()
    c = conn.cursor()
    
    # Проверяем владельца
    c.execute("SELECT owner FROM rooms WHERE id=?", (room_id,))
    owner_result = c.fetchone()
    if not owner_result or owner_result[0] != username:
        flash('Только создатель может начать игру', 'error')
        conn.close()
        return redirect(f'/room/{room_id}')
    
    # Количество участников
    c.execute("SELECT COUNT(*) FROM room_members WHERE room_id=?", (room_id,))
    count = c.fetchone()[0]
    
    if count > len(ROLES):
        flash(f'Максимум {len(ROLES)} человек', 'error')
    elif count < 2:
        flash('Нужно минимум 2 человека', 'error')
    else:
        # Получаем участников
        c.execute("SELECT username FROM room_members WHERE room_id=?", (room_id,))
        members = [row[0] for row in c.fetchall()]
        
        # Перемешиваем роли
        shuffled = ROLES.copy()
        random.shuffle(shuffled)
        
        # Назначаем роли
        for i, member in enumerate(members):
            if i < len(shuffled):
                c.execute("UPDATE room_members SET role=? WHERE room_id=? AND username=?",
                         (shuffled[i], room_id, member))
        
        # Стартуем игру
        c.execute("UPDATE rooms SET game_started=1 WHERE id=?", (room_id,))
        conn.commit()
        flash('Игра начата! Роли распределены!', 'success')
    
    conn.close()
    return redirect(f'/room/{room_id}')

@app.route('/reveal_role/<room_id>')
def reveal_role(room_id):
    if 'username' not in session:
        return redirect('/login')
    
    username = session['username']
    
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT role FROM room_members WHERE room_id=? AND username=?", 
             (room_id, username))
    role_result = c.fetchone()
    conn.close()
    
    if role_result and role_result[0]:
        flash(f'Ваша роль: {role_result[0]}', 'success')
    else:
        flash('Роли еще нет', 'error')
    
    return redirect(f'/room/{room_id}')

@app.route('/reset_game/<room_id>')
def reset_game(room_id):
    if 'username' not in session:
        return redirect('/login')
    
    username = session['username']
    
    conn = get_db()
    c = conn.cursor()
    
    # Проверяем владельца
    c.execute("SELECT owner FROM rooms WHERE id=?", (room_id,))
    owner_result = c.fetchone()
    
    if owner_result and owner_result[0] == username:
        c.execute("UPDATE room_members SET role=NULL WHERE room_id=?", (room_id,))
        c.execute("UPDATE rooms SET game_started=0 WHERE id=?", (room_id,))
        conn.commit()
        flash('Игра сброшена', 'info')
    else:
        flash('Только создатель может сбросить', 'error')
    
    conn.close()
    return redirect(f'/room/{room_id}')

@app.route('/leave_room/<room_id>')
def leave_room(room_id):
    if 'username' not in session:
        return redirect('/login')
    
    username = session['username']
    
    conn = get_db()
    c = conn.cursor()
    
    # Удаляем участника
    c.execute("DELETE FROM room_members WHERE room_id=? AND username=?", 
             (room_id, username))
    
    # Проверяем пустая ли комната
    c.execute("SELECT COUNT(*) FROM room_members WHERE room_id=?", (room_id,))
    if c.fetchone()[0] == 0:
        c.execute("DELETE FROM rooms WHERE id=?", (room_id,))
    
    conn.commit()
    conn.close()
    
    flash('Вы вышли из комнаты', 'info')
    return redirect('/')

if __name__ == '__main__':
    # Всегда создаем новую базу при запуске
    init_db()
    
    print("=" * 50)
    print("🎮 БУНКЕР ЗАПУЩЕН!")
    print("🌐 http://localhost:5000")
    print("=" * 50)
    
    app.run(debug=True, port=5000)