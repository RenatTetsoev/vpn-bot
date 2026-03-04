from flask import Flask, request, jsonify
from flask_cors import CORS
import sqlite3
from datetime import datetime
import logging

app = Flask(__name__)
CORS(app)

# Настройка логирования
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger(__name__)

DB_PATH = '/opt/vpnproxybot/vpn_database.db'

def get_db():
    """Подключение к существующей базе данных"""
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    return conn

@app.route('/ping', methods=['GET'])
def ping():
    return jsonify({'status': 'ok', 'message': 'VLESS API работает'})

@app.route('/check_key', methods=['POST'])
def check_key():
    try:
        data = request.json
        key = data.get('key')
        device_id = data.get('device_id', 'unknown')

        logger.info(f"🔍 Проверка ключа: {key}")

        conn = get_db()
        cursor = conn.cursor()
        
        # Ищем ключ в вашей таблице
        cursor.execute('SELECT * FROM vpn_keys WHERE key_value = ?', (key,))
        key_data = cursor.fetchone()

        if not key_data:
            logger.warning(f"❌ Ключ не найден: {key}")
            return jsonify({'valid': False, 'message': 'Ключ не найден'})

        # Преобразуем в dict
        key_dict = dict(key_data)
        
        # Проверка блокировки
        if key_dict.get('blocked', 0) == 1:
            logger.warning(f"❌ Ключ заблокирован: {key}")
            return jsonify({'valid': False, 'message': 'Ключ заблокирован'})

        # Проверка оплаты
        if key_dict.get('is_paid', 0) == 0:
            logger.warning(f"❌ Ключ не оплачен: {key}")
            return jsonify({'valid': False, 'message': 'Ключ не оплачен'})

        # Проверка срока действия
        expiry = datetime.fromisoformat(key_dict['expiry_date'])
        now = datetime.now()

        if now > expiry:
            logger.warning(f"❌ Срок ключа истек: {key}")
            return jsonify({'valid': False, 'message': 'Срок действия истек'})

        days_left = (expiry - now).days
        
        # Обновляем last_used
        cursor.execute('UPDATE vpn_keys SET last_used = ? WHERE key_value = ?',
                      (now.isoformat(), key))
        
        # Если device_id не привязан - привязываем
        if not key_dict.get('device_id'):
            cursor.execute('UPDATE vpn_keys SET device_id = ? WHERE key_value = ?',
                          (device_id, key))
            logger.info(f"✅ Ключ {key} привязан к устройству {device_id}")
        
        conn.commit()
        conn.close()

        return jsonify({
            'valid': True,
            'message': 'Ключ действителен',
            'key_info': {
                'key': key,
                'client_id': key_dict['client_id'],
                'expiry_date': key_dict['expiry_date'],
                'days_left': days_left
            }
        })
        
    except Exception as e:
        logger.error(f"❌ Ошибка: {str(e)}")
        return jsonify({'valid': False, 'message': f'Ошибка: {str(e)}'})

@app.route('/get_vless_config', methods=['POST'])
def get_vless_config():
    try:
        data = request.json
        key = data.get('key')
        logger.info(f"📡 Запрос конфига для ключа: {key}")

        conn = get_db()
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM vpn_keys WHERE key_value = ?', (key,))
        key_data = cursor.fetchone()
        conn.close()

        if not key_data:
            return jsonify({'success': False, 'message': 'Ключ не найден'})

        key_dict = dict(key_data)
        
        # Проверки
        if key_dict.get('is_paid', 0) == 0:
            return jsonify({'success': False, 'message': 'Ключ не оплачен'})

        if key_dict.get('blocked', 0) == 1:
            return jsonify({'success': False, 'message': 'Ключ заблокирован'})

        # Конфиг для клиента
        vless_config = {
            'client_id': key_dict['client_id'],
            'server': '95.81.102.13',
            'port': 443,
            'security': 'none',
            'type': 'tcp',
            'headerType': 'http',
            'host': 'www.google.com',
            'path': '/',
            'tls': False
        }

        return jsonify({'success': True, 'config': vless_config})
        
    except Exception as e:
        logger.error(f"❌ Ошибка: {str(e)}")
        return jsonify({'success': False, 'message': str(e)})

@app.route('/debug/keys', methods=['GET'])
def debug_keys():
    """Для отладки - список ключей"""
    try:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT key_value, client_id, is_paid, blocked, device_id, expiry_date 
            FROM vpn_keys LIMIT 10
        ''')
        keys = cursor.fetchall()
        conn.close()
        return jsonify({'keys': [dict(k) for k in keys]})
    except Exception as e:
        return jsonify({'error': str(e)})

if __name__ == '__main__':
    print("🚀 VLESS API СЕРВЕР ЗАПУЩЕН")
    print(f"📁 БД: {DB_PATH}")
    print(f"🌐 Порт: 5000")
    app.run(host='0.0.0.0', port=5000, debug=True)
