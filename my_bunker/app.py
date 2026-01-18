from flask import Flask, render_template, request, jsonify, session
from flask_cors import CORS
import hashlib
import secrets
import random
import time
from datetime import datetime

app = Flask(__name__)
app.secret_key = 'bunker-key-123-super-secret-2024'
app.config['SESSION_TYPE'] = 'filesystem'
app.config['PERMANENT_SESSION_LIFETIME'] = 3600  # 1 час
CORS(app, supports_credentials=True, origins=["http://localhost:5000", "http://127.0.0.1:5000"])

ROLES = ["👨‍🍳 Повар", "👮 Полицейский", "👨‍🔬 Ученый", "👨‍🔬 Биолог", "👨‍🔬 Физик", "🏃 Спортсмен"]

# ========== ХРАНИЛИЩА В ПАМЯТИ ==========
users_db = {}  # {username: {password_hash, created}}
rooms_db = {}  # {room_id: {id, name, owner, members, game_started, roles, created_at}}

# ========== ХЕЛПЕРЫ ==========
def hash_password(pwd):
    return hashlib.sha256(pwd.encode()).hexdigest()

def gen_room_id():
    return 'room_' + secrets.token_hex(8)

def get_current_user():
    return session.get('username')

# ========== API ДЛЯ КЛИЕНТА ==========
@app.route('/api/register', methods=['POST'])
def api_register():
    """Регистрация пользователя"""
    try:
        data = request.json
        if not data:
            return jsonify({'success': False, 'message': 'Нет данных'}), 400
            
        username = data.get('username', '').strip()
        password = data.get('password', '')
        
        if not username or not password:
            return jsonify({'success': False, 'message': 'Заполните все поля'}), 400
        
        if len(username) < 3:
            return jsonify({'success': False, 'message': 'Имя от 3 символов'}), 400
        
        if len(password) < 6:
            return jsonify({'success': False, 'message': 'Пароль от 6 символов'}), 400
        
        if username in users_db:
            return jsonify({'success': False, 'message': 'Пользователь уже существует'}), 400
        
        users_db[username] = {
            'password_hash': hash_password(password),
            'created': datetime.now().isoformat()
        }
        
        session['username'] = username
        session.permanent = True
        
        return jsonify({
            'success': True, 
            'message': 'Регистрация успешна', 
            'username': username
        })
        
    except Exception as e:
        return jsonify({'success': False, 'message': f'Ошибка сервера: {str(e)}'}), 500

@app.route('/api/login', methods=['POST'])
def api_login():
    """Вход пользователя"""
    try:
        data = request.json
        username = data.get('username', '').strip()
        password = data.get('password', '')
        
        user = users_db.get(username)
        if not user or user['password_hash'] != hash_password(password):
            return jsonify({'success': False, 'message': 'Неверный логин или пароль'}), 401
        
        session['username'] = username
        session.permanent = True
        
        return jsonify({
            'success': True, 
            'message': 'Вход выполнен', 
            'username': username
        })
        
    except Exception as e:
        return jsonify({'success': False, 'message': f'Ошибка: {str(e)}'}), 500

@app.route('/api/logout', methods=['POST'])
def api_logout():
    """Выход"""
    session.pop('username', None)
    return jsonify({'success': True, 'message': 'Вы вышли'})

@app.route('/api/user', methods=['GET'])
def api_get_user():
    """Получить текущего пользователя"""
    username = session.get('username')
    return jsonify({'success': True, 'username': username})

@app.route('/api/rooms', methods=['GET'])
def api_get_rooms():
    """Получить список комнат пользователя"""
    username = get_current_user()
    if not username:
        return jsonify({'success': False, 'message': 'Нет авторизации'}), 401
    
    # Комнаты где пользователь является участником
    user_rooms = []
    for room_id, room in rooms_db.items():
        if username in room['members']:
            user_rooms.append({
                'id': room_id,
                'name': room['name'],
                'owner': room['owner'],
                'members_count': len(room['members']),
                'game_started': room['game_started']
            })
    
    return jsonify({'success': True, 'rooms': user_rooms})

@app.route('/api/rooms/create', methods=['POST'])
def api_create_room():
    """Создать комнату"""
    username = get_current_user()
    if not username:
        return jsonify({'success': False, 'message': 'Нет авторизации'}), 401
    
    try:
        data = request.json
        room_name = data.get('name', f'Комната {username}').strip()
        
        room_id = gen_room_id()
        rooms_db[room_id] = {
            'id': room_id,
            'name': room_name,
            'owner': username,
            'members': [username],
            'game_started': False,
            'roles': {},
            'created_at': datetime.now().isoformat()
        }
        
        return jsonify({
            'success': True, 
            'message': 'Комната создана',
            'room': {
                'id': room_id,
                'name': room_name,
                'owner': username
            }
        })
        
    except Exception as e:
        return jsonify({'success': False, 'message': f'Ошибка: {str(e)}'}), 500

@app.route('/api/rooms/<room_id>', methods=['GET'])
def api_get_room(room_id):
    """Получить информацию о комнате"""
    username = get_current_user()
    if not username:
        return jsonify({'success': False, 'message': 'Нет авторизации'}), 401
    
    room = rooms_db.get(room_id)
    if not room:
        return jsonify({'success': False, 'message': 'Комната не найдена'}), 404
    
    # Добавляем пользователя если его нет
    if username not in room['members']:
        room['members'].append(username)
    
    return jsonify({
        'success': True,
        'room': {
            'id': room_id,
            'name': room['name'],
            'owner': room['owner'],
            'members': room['members'],
            'game_started': room['game_started'],
            'roles': room['roles'],
            'user_role': room['roles'].get(username),
            'is_owner': room['owner'] == username
        }
    })

@app.route('/api/rooms/<room_id>/join', methods=['POST'])
def api_join_room(room_id):
    """Присоединиться к комнате"""
    username = get_current_user()
    if not username:
        return jsonify({'success': False, 'message': 'Нет авторизации'}), 401
    
    room = rooms_db.get(room_id)
    if not room:
        return jsonify({'success': False, 'message': 'Комната не найдена'}), 404
    
    if username not in room['members']:
        room['members'].append(username)
    
    return jsonify({
        'success': True,
        'message': 'Вы в комнате',
        'room': {
            'id': room_id,
            'name': room['name'],
            'owner': room['owner']
        }
    })

@app.route('/api/rooms/<room_id>/start', methods=['POST'])
def api_start_game(room_id):
    """Начать игру"""
    username = get_current_user()
    if not username:
        return jsonify({'success': False, 'message': 'Нет авторизации'}), 401
    
    room = rooms_db.get(room_id)
    if not room:
        return jsonify({'success': False, 'message': 'Комната не найдена'}), 404
    
    # Проверяем что пользователь - владелец
    if room['owner'] != username:
        return jsonify({'success': False, 'message': 'Только создатель может начать игру'}), 403
    
    # Проверяем количество участников
    if len(room['members']) < 2:
        return jsonify({'success': False, 'message': 'Нужно минимум 2 человека'}), 400
    
    if len(room['members']) > len(ROLES):
        return jsonify({'success': False, 'message': f'Максимум {len(ROLES)} человек'}), 400
    
    # Распределяем роли
    shuffled_roles = ROLES.copy()
    random.shuffle(shuffled_roles)
    
    room['roles'] = {}
    for i, member in enumerate(room['members']):
        if i < len(shuffled_roles):
            room['roles'][member] = shuffled_roles[i]
    
    room['game_started'] = True
    
    return jsonify({
        'success': True,
        'message': 'Игра начата! Роли распределены',
        'roles': room['roles']
    })

@app.route('/api/rooms/<room_id>/leave', methods=['POST'])
def api_leave_room(room_id):
    """Выйти из комнаты"""
    username = get_current_user()
    if not username:
        return jsonify({'success': False, 'message': 'Нет авторизации'}), 401
    
    room = rooms_db.get(room_id)
    if not room:
        return jsonify({'success': True, 'message': 'Комнаты уже нет'})
    
    if username in room['members']:
        room['members'].remove(username)
        
        # Если комната пустая - удаляем её
        if len(room['members']) == 0:
            rooms_db.pop(room_id, None)
        # Если вышел владелец - назначаем нового
        elif room['owner'] == username and room['members']:
            room['owner'] = room['members'][0]
    
    return jsonify({'success': True, 'message': 'Вы вышли из комнаты'})

@app.route('/api/rooms/<room_id>/reset', methods=['POST'])
def api_reset_game(room_id):
    """Сбросить игру"""
    username = get_current_user()
    if not username:
        return jsonify({'success': False, 'message': 'Нет авторизации'}), 401
    
    room = rooms_db.get(room_id)
    if not room:
        return jsonify({'success': False, 'message': 'Комната не найдена'}), 404
    
    # Проверяем что пользователь - владелец
    if room['owner'] != username:
        return jsonify({'success': False, 'message': 'Только создатель может сбросить игру'}), 403
    
    # Сбрасываем игру
    room['game_started'] = False
    room['roles'] = {}
    
    return jsonify({'success': True, 'message': 'Игра сброшена'})

@app.route('/api/health', methods=['GET'])
def api_health():
    """Проверка здоровья сервера"""
    return jsonify({
        'status': 'ok',
        'timestamp': datetime.now().isoformat(),
        'users_count': len(users_db),
        'rooms_count': len(rooms_db)
    })

# ========== ОСНОВНОЙ МАРШРУТ ==========
@app.route('/')
def index():
    """Отдаём главную страницу"""
    return render_template('index.html')

@app.route('/<path:path>')
def static_files(path):
    """Отдаём статические файлы"""
    return app.send_static_file(path) if hasattr(app, 'static_folder') else f"File {path} not found", 404

# ========== ЗАПУСК ==========
if __name__ == '__main__':
    print("=" * 60)
    print("🎮 БУНКЕР СЕРВЕР ЗАПУЩЕН!")
    print("🌐 http://localhost:5000")
    print("=" * 60)
    print("📡 Доступные API endpoints:")
    print("  POST /api/register     - регистрация")
    print("  POST /api/login        - вход")
    print("  GET  /api/rooms        - список комнат")
    print("  POST /api/rooms/create - создать комнату")
    print("  GET  /api/rooms/<id>   - получить комнату")
    print("  POST /api/rooms/<id>/start - начать игру")
    print("  POST /api/rooms/<id>/leave - выйти")
    print("  GET  /api/health       - статус сервера")
    print("=" * 60)
    print("💡 Подсказка:")
    print("  1. Откройте http://localhost:5000 в браузере")
    print("  2. Зарегистрируйтесь или войдите")
    print("  3. Создайте комнату и отправьте ссылку другу")
    print("  4. Начните игру когда все присоединятся")
    print("=" * 60)
    
    app.run(debug=True, port=5000, host='0.0.0.0', threaded=True)