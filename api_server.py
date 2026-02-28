from flask import Flask, request, jsonify
from flask_cors import CORS
import sqlite3
from datetime import datetime
import sys

app = Flask(__name__)
CORS(app)


def log_message(msg):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] {msg}")
    sys.stdout.flush()


def get_db():
    conn = sqlite3.connect('vpn_database.db', timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA journal_mode=WAL')
    return conn


@app.after_request
def add_header(response):
    response.headers['Content-Type'] = 'application/json'
    response.headers['Access-Control-Allow-Origin'] = '*'
    return response


@app.route('/ping', methods=['GET'])
def ping():
    return jsonify({'status': 'ok', 'message': 'VLESS сервер работает!'})


@app.route('/check_key', methods=['POST'])
def check_key():
    try:
        data = request.json
        key = data.get('key')
        device_info = data.get('device_info', {})
        device_id = device_info.get('device', 'unknown')

        log_message(f"🔍 Проверка ключа: {key} с устройства {device_id}")

        conn = get_db()
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM vless_keys WHERE key_value = ?', (key,))
        key_data = cursor.fetchone()

        if not key_data:
            return jsonify({'valid': False, 'message': '❌ Ключ не найден'})

        # Проверка оплаты
        if not key_data['is_paid']:
            return jsonify({'valid': False, 'message': '❌ Ключ не оплачен'})

        if key_data['is_blocked']:
            return jsonify({'valid': False, 'message': '❌ Ключ заблокирован'})

        # Проверка на одно устройство
        if key_data['is_active'] and key_data['device_id'] and key_data['device_id'] != device_id:
            return jsonify({'valid': False, 'message': '❌ Ключ уже используется на другом устройстве'})

        expiry = datetime.fromisoformat(key_data['expiry_date'])
        now = datetime.now()

        if now > expiry:
            return jsonify({'valid': False, 'message': '❌ Срок действия истек'})

        days_left = (expiry - now).days

        # Если ключ активируется впервые
        if not key_data['is_active']:
            cursor.execute('''
                UPDATE vless_keys 
                SET is_active = 1, activation_date = ?, device_id = ?, last_used = ? 
                WHERE key_value = ?
            ''', (now.isoformat(), device_id, now.isoformat(), key))
            conn.commit()
            log_message(f"✅ Ключ {key} активирован на устройстве {device_id}")
        else:
            cursor.execute('UPDATE vless_keys SET last_used = ? WHERE key_value = ?',
                           (now.isoformat(), key))
            conn.commit()

        conn.close()

        return jsonify({
            'valid': True,
            'message': '✅ Ключ действителен',
            'key_info': {
                'key': key,
                'client_id': key_data['client_id'],
                'activation_date': key_data['activation_date'] or now.isoformat(),
                'expiry_date': key_data['expiry_date'],
                'days_left': days_left
            }
        })
    except Exception as e:
        log_message(f"❌ Ошибка: {str(e)}")
        return jsonify({'valid': False, 'message': f'❌ Ошибка: {str(e)}'})


@app.route('/get_vless_config', methods=['POST'])
def get_vless_config():
    try:
        data = request.json
        key = data.get('key')
        log_message(f"📡 Запрос конфига для ключа: {key}")

        conn = get_db()
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM vless_keys WHERE key_value = ?', (key,))
        key_data = cursor.fetchone()

        if not key_data:
            return jsonify({'success': False, 'message': 'Ключ не найден'})

        if not key_data['is_paid']:
            return jsonify({'success': False, 'message': 'Ключ не оплачен'})

        vless_config = {
            'client_id': key_data['client_id'],
            'server': '95.81.102.13',
            'port': 443,
            'security': 'none',
            'type': 'tcp',
            'headerType': 'http',
            'host': 'www.google.com',
            'path': '/',
            'tls': False
        }

        log_message(f"📤 Отправка конфига для ключа {key}")
        return jsonify({'success': True, 'config': vless_config})
    except Exception as e:
        log_message(f"❌ Ошибка: {str(e)}")
        return jsonify({'success': False, 'message': str(e)})


@app.route('/debug/keys', methods=['GET'])
def debug_keys():
    try:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute(
            'SELECT id, key_value, client_id, email, is_paid, is_active, device_id, expiry_date FROM vless_keys')
        keys = cursor.fetchall()
        conn.close()
        keys_list = [dict(key) for key in keys]
        return jsonify({'count': len(keys_list), 'keys': keys_list})
    except Exception as e:
        return jsonify({'error': str(e)})


if __name__ == '__main__':
    print("=" * 60)
    print("🚀 ЗАПУСК VLESS API СЕРВЕРА")
    print("=" * 60)
    print(f"📁 База данных: vpn_database.db")
    print(f"🌐 Сервер: 95.81.102.13:5000")
    print("=" * 60)
    app.run(host='0.0.0.0', port=5000, debug=True)