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
    return jsonify({'status': 'ok', 'message': 'VPN сервер работает!'})


@app.route('/check_key', methods=['POST'])
def check_key():
    try:
        data = request.json
        key = data.get('key')
        device_info = data.get('device_info', {})
        device_id = device_info.get('device', 'unknown')

        log_message(f"🔍 Проверка ключа: {key}")

        conn = get_db()
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM vpn_keys WHERE key_value = ?', (key,))
        key_data = cursor.fetchone()

        if not key_data:
            return jsonify({'valid': False, 'message': '❌ Ключ не найден'})

        if not key_data['is_paid']:
            return jsonify({'valid': False, 'message': '❌ Ключ не оплачен'})

        expiry = datetime.fromisoformat(key_data['expiry_date'])
        now = datetime.now()

        if now > expiry:
            return jsonify({'valid': False, 'message': '❌ Срок действия истек'})

        days_left = (expiry - now).days

        return jsonify({
            'valid': True,
            'message': '✅ Ключ действителен',
            'key_info': {
                'key': key,
                'client_id': key_data['client_id'],
                'expiry_date': key_data['expiry_date'],
                'days_left': days_left
            }
        })
    except Exception as e:
        return jsonify({'valid': False, 'message': f'❌ Ошибка: {str(e)}'})


@app.route('/get_config', methods=['POST'])
def get_config():
    try:
        data = request.json
        key = data.get('key')

        conn = get_db()
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM vpn_keys WHERE key_value = ?', (key,))
        key_data = cursor.fetchone()

        if not key_data:
            return jsonify({'success': False, 'message': 'Ключ не найден'})

        if not key_data['is_paid']:
            return jsonify({'success': False, 'message': 'Ключ не оплачен'})

        config = {
            'client_id': key_data['client_id'],
            'server': '95.81.102.13',
            'port': 443,
            'security': 'none',
            'type': 'tcp',
            'headerType': 'http',
            'host': 'www.google.com',
            'path': '/'
        }

        return jsonify({'success': True, 'config': config})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})


if __name__ == '__main__':
    print("=" * 60)
    print("🚀 ЗАПУСК VPN API СЕРВЕРА")
    print("=" * 60)
    print(f"🌐 Сервер: 95.81.102.13:5000")
    print("=" * 60)
    app.run(host='0.0.0.0', port=5000, debug=True)