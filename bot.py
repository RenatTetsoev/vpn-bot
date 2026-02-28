import telebot
import uuid
import sqlite3
import random
import string
import json
import threading
import time
import requests
import subprocess
from datetime import datetime, timedelta
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

TOKEN = '8632835912:AAFesJq2qhoBw4N_h5cmB-fVQauvvOwpUwQ'
bot = telebot.TeleBot(TOKEN)

# ========== НАСТРОЙКИ ==========
SERVER_IP = "95.81.102.13"
SERVER_PORT = 443
PRICE_USDT = 1.50
ORDER_LIFETIME = 10

# 👇 ТВОЙ TELEGRAM ID (АДМИН)
ADMIN_ID = 1684751552

CRYPTO_API_TOKEN = "540507:AAyXFAZkerRA5kUrrlOmNHs1mV4xZuBZKeO"
BOT_USERNAME = "vpnconnecting_bot"


# ========== ФУНКЦИЯ ДОБАВЛЕНИЯ В XRAY ==========
def add_client_to_xray(client_id, email):
    """Добавляет клиента в конфиг Xray и перезапускает сервис"""
    try:
        # Читаем текущий конфиг
        with open('/usr/local/etc/xray/config.json', 'r') as f:
            config = json.load(f)

        # Добавляем нового клиента
        new_client = {
            "id": client_id,
            "email": email,
            "level": 0
        }

        config['inbounds'][0]['settings']['clients'].append(new_client)

        # Записываем обновленный конфиг
        with open('/usr/local/etc/xray/config.json', 'w') as f:
            json.dump(config, f, indent=2)

        # Перезапускаем Xray
        subprocess.run(['systemctl', 'restart', 'xray'])
        print(f"✅ Клиент {client_id} добавлен в Xray")
        return True
    except Exception as e:
        print(f"❌ Ошибка добавления клиента в Xray: {e}")
        return False


# ========== БАЗА ДАННЫХ ==========
def get_db():
    conn = sqlite3.connect('vpn_database.db')
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS vpn_keys (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        key_value TEXT UNIQUE NOT NULL,
        client_id TEXT UNIQUE NOT NULL,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        expiry_date DATETIME,
        is_paid BOOLEAN DEFAULT 0,
        payment_time DATETIME,
        telegram_id TEXT,
        invoice_id TEXT UNIQUE,
        is_free BOOLEAN DEFAULT 0
    )
    ''')
    conn.commit()
    conn.close()
    print("✅ База данных готова")


init_db()

orders = {}


def generate_key():
    client_id = str(uuid.uuid4())
    access_key = 'VPN-' + ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))
    return client_id, access_key


def format_datetime(dt):
    return dt.strftime('%d.%m.%Y %H:%M:%S')


def create_crypto_invoice(amount, description):
    """Создает одноразовый счет в CryptoBot"""
    try:
        url = "https://pay.crypt.bot/api/createInvoice"
        headers = {
            "Crypto-Pay-API-Token": CRYPTO_API_TOKEN,
            "Content-Type": "application/json"
        }
        data = {
            "asset": "USDT",
            "amount": str(amount),
            "description": description,
            "paid_btn_name": "openBot",
            "paid_btn_url": f"https://t.me/{BOT_USERNAME}",
            "allow_comments": False,
            "allow_anonymous": False,
            "expires_in": 600
        }

        response = requests.post(url, headers=headers, json=data)
        result = response.json()

        if result.get("ok"):
            invoice_id = result["result"]["invoice_id"]
            pay_url = result["result"]["pay_url"]
            print(f"✅ Чек создан: {pay_url}")
            return invoice_id, pay_url
        else:
            print(f"❌ Ошибка API: {result}")
            return None, None
    except Exception as e:
        print(f"❌ Ошибка создания чека: {e}")
        return None, None


def check_invoice_status(invoice_id):
    """Проверяет статус счета"""
    try:
        url = "https://pay.crypt.bot/api/getInvoices"
        headers = {"Crypto-Pay-API-Token": CRYPTO_API_TOKEN}
        params = {"invoice_ids": invoice_id}

        response = requests.get(url, headers=headers, params=params)
        result = response.json()

        if result.get("ok") and result["result"]["items"]:
            status = result["result"]["items"][0]["status"]
            print(f"📊 Статус счета {invoice_id}: {status}")
            return status == "paid"
        return False
    except Exception as e:
        print(f"❌ Ошибка проверки: {e}")
        return False


# ========== КНОПКИ ==========
def main_menu():
    keyboard = InlineKeyboardMarkup(row_width=1)
    btn1 = InlineKeyboardButton("💰 Купить VPN", callback_data="buy_vpn")
    btn2 = InlineKeyboardButton("🔑 Мои ключи", callback_data="my_keys")
    btn3 = InlineKeyboardButton("❓ Помощь", callback_data="help")
    keyboard.add(btn1, btn2, btn3)
    return keyboard


def admin_menu():
    keyboard = InlineKeyboardMarkup(row_width=1)
    btn1 = InlineKeyboardButton("🎁 Выдать бесплатный ключ", callback_data="admin_free_key")
    btn2 = InlineKeyboardButton("📊 Статистика", callback_data="admin_stats")
    btn3 = InlineKeyboardButton("🔙 Закрыть админ-панель", callback_data="close_admin")
    keyboard.add(btn1, btn2, btn3)
    return keyboard


def confirm_menu():
    keyboard = InlineKeyboardMarkup(row_width=2)
    btn1 = InlineKeyboardButton("✅ Да, принимаю", callback_data="accept_rules")
    btn2 = InlineKeyboardButton("❌ Нет", callback_data="main_menu")
    keyboard.add(btn1, btn2)
    return keyboard


def payment_menu(key, pay_url):
    keyboard = InlineKeyboardMarkup(row_width=1)
    btn1 = InlineKeyboardButton("💳 Оплатить 1.5 USDT", url=pay_url)
    btn2 = InlineKeyboardButton("✅ Я оплатил, проверить", callback_data=f"check_payment_{key}")
    btn3 = InlineKeyboardButton("❌ Отменить заказ", callback_data="cancel_order")
    btn4 = InlineKeyboardButton("🏠 Главное меню", callback_data="main_menu")
    keyboard.add(btn1, btn2, btn3, btn4)
    return keyboard


def back_menu():
    keyboard = InlineKeyboardMarkup()
    btn = InlineKeyboardButton("🏠 Главное меню", callback_data="main_menu")
    keyboard.add(btn)
    return keyboard


# ========== ОБРАБОТЧИК КОМАНД ==========
@bot.message_handler(commands=['start'])
def start(message):
    text = (
        "🔐 **VPN CONNECTING**\n\n"
        "⚡️ Высокоскоростной VPN\n"
        "📱 1 ключ = 1 устройство\n"
        "📅 Срок действия: 30 дней\n\n"
        f"💰 **Цена:** {PRICE_USDT} USDT\n\n"
        "Выберите действие:"
    )
    bot.send_message(message.chat.id, text, parse_mode='Markdown', reply_markup=main_menu())


# ========== АДМИН-ПАНЕЛЬ ==========
@bot.message_handler(commands=['adminpanel'])
def admin_panel(message):
    """Секретная команда для админа"""
    if message.from_user.id != ADMIN_ID:
        bot.reply_to(message, "❌ У вас нет доступа к админ-панели")
        return

    text = (
        "🔐 **АДМИН-ПАНЕЛЬ**\n\n"
        "Добро пожаловать, администратор!\n"
        "Выберите действие:"
    )
    bot.send_message(message.chat.id, text, parse_mode='Markdown', reply_markup=admin_menu())


@bot.callback_query_handler(func=lambda call: True)
def handle_callback(call):
    user_id = call.from_user.id
    data = call.data

    if data == "main_menu":
        text = "🔐 **VPN CONNECTING**\n\nВыберите действие:"
        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text=text,
            parse_mode='Markdown',
            reply_markup=main_menu()
        )
        bot.answer_callback_query(call.id)

    elif data == "close_admin":
        text = "🔐 **VPN CONNECTING**\n\nАдмин-панель закрыта."
        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text=text,
            parse_mode='Markdown',
            reply_markup=main_menu()
        )
        bot.answer_callback_query(call.id)

    elif data == "admin_free_key":
        if user_id != ADMIN_ID:
            bot.answer_callback_query(call.id, "❌ Доступ запрещен", show_alert=True)
            return

        client_id, key = generate_key()
        expiry = datetime.now() + timedelta(days=30)

        conn = get_db()
        cursor = conn.cursor()
        cursor.execute('''
        INSERT INTO vpn_keys (key_value, client_id, expiry_date, telegram_id, is_paid, is_free)
        VALUES (?, ?, ?, ?, ?, ?)
        ''', (key, client_id, expiry.isoformat(), str(user_id), 1, 1))
        conn.commit()
        conn.close()

        # 👇 ДОБАВЛЯЕМ В XRAY
        add_client_to_xray(client_id, f"admin_free_{key}")

        link = f"vless://{client_id}@{SERVER_IP}:{SERVER_PORT}?security=none&type=tcp&headerType=http&host=www.google.com#{key}"

        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text=f"✅ **Бесплатный ключ сгенерирован и добавлен в Xray!**\n\n"
                 f"🔑 **Ключ:** `{key}`\n"
                 f"🔗 **VLESS ссылка:**\n`{link}`\n\n"
                 f"📅 **Действует до:** {format_datetime(expiry)}",
            parse_mode='Markdown',
            reply_markup=admin_menu()
        )
        bot.answer_callback_query(call.id, "Ключ создан и добавлен в Xray!")

    elif data == "admin_stats":
        if user_id != ADMIN_ID:
            bot.answer_callback_query(call.id, "❌ Доступ запрещен", show_alert=True)
            return

        conn = get_db()
        cursor = conn.cursor()
        cursor.execute('SELECT COUNT(*) as total FROM vpn_keys')
        total = cursor.fetchone()['total']

        cursor.execute('SELECT COUNT(*) as paid FROM vpn_keys WHERE is_paid = 1')
        paid = cursor.fetchone()['paid']

        cursor.execute('SELECT COUNT(*) as free FROM vpn_keys WHERE is_free = 1')
        free = cursor.fetchone()['free']

        cursor.execute(
            'SELECT COUNT(*) as active FROM vpn_keys WHERE is_paid = 1 AND datetime(expiry_date) > datetime("now")')
        active = cursor.fetchone()['active']
        conn.close()

        text = (
            f"📊 **СТАТИСТИКА**\n\n"
            f"🔑 Всего ключей: {total}\n"
            f"✅ Оплаченных: {paid}\n"
            f"🎁 Бесплатных: {free}\n"
            f"⚡️ Активных: {active}"
        )

        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text=text,
            parse_mode='Markdown',
            reply_markup=admin_menu()
        )
        bot.answer_callback_query(call.id)

    elif data == "help":
        text = (
            "❓ **Помощь**\n\n"
            "1. Нажмите 'Купить VPN'\n"
            "2. Примите правила\n"
            "3. Оплатите через CryptoBot\n"
            "4. Нажмите 'Я оплатил'\n"
            "5. Получите VPN ссылку\n\n"
            "📱 Для подключения используйте v2rayNG"
        )
        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text=text,
            parse_mode='Markdown',
            reply_markup=back_menu()
        )
        bot.answer_callback_query(call.id)

    elif data == "my_keys":
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute(
            'SELECT key_value, expiry_date, is_paid FROM vpn_keys WHERE telegram_id = ? ORDER BY created_at DESC',
            (str(user_id),)
        )
        keys = cursor.fetchall()
        conn.close()

        if not keys:
            text = "🔑 **Ваши ключи**\n\nУ вас пока нет ключей."
        else:
            text = "🔑 **Ваши ключи**\n\n"
            for key in keys:
                expiry = datetime.fromisoformat(key['expiry_date']).strftime('%d.%m.%Y')
                status = "✅" if key['is_paid'] else "⏳"
                text += f"{status} `{key['key_value']}` до {expiry}\n"

        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text=text,
            parse_mode='Markdown',
            reply_markup=back_menu()
        )
        bot.answer_callback_query(call.id)

    elif data == "buy_vpn":
        if user_id in orders:
            bot.answer_callback_query(
                call.id,
                "У вас уже есть активный заказ! Сначала отмените его.",
                show_alert=True
            )
            return

        text = (
            "⚠️ **ПРАВИЛА ИСПОЛЬЗОВАНИЯ**\n\n"
            "❗️ Вы берете на себя всю ответственность за использование данного VPN.\n\n"
            "• Разработчик бота и сервиса не несет ответственности за ваши действия\n"
            "• Использование VPN может регулироваться законодательством вашей страны\n"
            "• Вы обязуетесь соблюдать все применимые законы\n\n"
            "Продолжая, вы подтверждаете согласие с данными условиями."
        )
        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text=text,
            parse_mode='Markdown',
            reply_markup=confirm_menu()
        )
        bot.answer_callback_query(call.id)

    elif data == "accept_rules":
        if user_id in orders:
            bot.answer_callback_query(call.id, "У вас уже есть заказ")
            return

        client_id, key = generate_key()
        expiry = datetime.now() + timedelta(days=30)

        invoice_id, pay_url = create_crypto_invoice(PRICE_USDT, f"VPN ключ {key}")

        if not invoice_id:
            bot.answer_callback_query(
                call.id,
                "Ошибка создания счета. Попробуйте позже.",
                show_alert=True
            )
            return

        conn = get_db()
        cursor = conn.cursor()
        cursor.execute('''
        INSERT INTO vpn_keys (key_value, client_id, expiry_date, telegram_id, is_paid, invoice_id)
        VALUES (?, ?, ?, ?, ?, ?)
        ''', (key, client_id, expiry.isoformat(), str(user_id), 0, invoice_id))
        conn.commit()
        conn.close()

        orders[user_id] = {'key': key, 'time': time.time(), 'invoice_id': invoice_id}

        text = (
            f"✅ **Ключ сгенерирован:** `{key}`\n\n"
            f"💰 **Сумма к оплате:** {PRICE_USDT} USDT\n"
            f"⏱ **Ссылка действительна 10 минут**\n\n"
            f"1. Нажмите кнопку 'Оплатить'\n"
            f"2. Оплатите в CryptoBot\n"
            f"3. Вернитесь и нажмите 'Проверить'"
        )
        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text=text,
            parse_mode='Markdown',
            reply_markup=payment_menu(key, pay_url)
        )
        bot.answer_callback_query(call.id, "Ключ создан!")

    elif data.startswith("check_payment_"):
        key = data.replace("check_payment_", "")

        if user_id not in orders or orders[user_id]['key'] != key:
            bot.answer_callback_query(call.id, "Заказ не найден", show_alert=True)
            return

        invoice_id = orders[user_id]['invoice_id']

        if check_invoice_status(invoice_id):
            conn = get_db()
            cursor = conn.cursor()
            cursor.execute('SELECT client_id, expiry_date FROM vpn_keys WHERE key_value = ?', (key,))
            data = cursor.fetchone()

            if data:
                client_id = data['client_id']

                # 👇 ДОБАВЛЯЕМ В XRAY
                add_client_to_xray(client_id, f"user_{user_id}_{key}")

                # Обновляем статус оплаты
                cursor.execute('''
                UPDATE vpn_keys SET is_paid = 1, payment_time = ? WHERE key_value = ?
                ''', (datetime.now().isoformat(), key))
                conn.commit()

                link = f"vless://{client_id}@{SERVER_IP}:{SERVER_PORT}?security=none&type=tcp&headerType=http&host=www.google.com#{key}"

                bot.send_message(
                    user_id,
                    f"✅ **ОПЛАЧЕНО!**\n\n"
                    f"🔑 **Ключ:** `{key}`\n"
                    f"🔗 **VPN CONNECTING ссылка:**\n`{link}`\n\n"
                    f"📅 **Действует до:** {format_datetime(datetime.fromisoformat(data['expiry_date']))}",
                    parse_mode='Markdown',
                    reply_markup=main_menu()
                )

                if user_id in orders:
                    del orders[user_id]

                bot.edit_message_text(
                    chat_id=call.message.chat.id,
                    message_id=call.message.message_id,
                    text="✅ Платеж подтвержден! Ключ отправлен в личные сообщения и добавлен в Xray.",
                    reply_markup=main_menu()
                )
                bot.answer_callback_query(call.id, "Ключ активирован!")
            conn.close()
        else:
            bot.answer_callback_query(
                call.id,
                "❌ Платеж не найден. Убедитесь, что вы оплатили, и попробуйте снова.",
                show_alert=True
            )

    elif data == "cancel_order":
        if user_id in orders:
            key = orders[user_id]['key']
            conn = get_db()
            cursor = conn.cursor()
            cursor.execute('DELETE FROM vpn_keys WHERE key_value = ? AND is_paid = 0', (key,))
            conn.commit()
            conn.close()
            del orders[user_id]

            bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text="❌ **Заказ отменен**\n\nВы можете создать новый заказ.",
                reply_markup=main_menu()
            )
            bot.answer_callback_query(call.id, "Заказ отменен")
        else:
            bot.answer_callback_query(call.id, "Нет активного заказа")


# ========== КОМАНДА MYKEYS ==========
@bot.message_handler(commands=['mykeys'])
def my_keys(message):
    user_id = message.from_user.id
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        'SELECT key_value, expiry_date, is_paid FROM vpn_keys WHERE telegram_id = ? ORDER BY created_at DESC',
        (str(user_id),)
    )
    keys = cursor.fetchall()
    conn.close()

    if not keys:
        text = "🔑 **Ваши ключи**\n\nУ вас пока нет ключей."
    else:
        text = "🔑 **Ваши ключи**\n\n"
        for key in keys:
            expiry = datetime.fromisoformat(key['expiry_date']).strftime('%d.%m.%Y')
            status = "✅" if key['is_paid'] else "⏳"
            text += f"{status} `{key['key_value']}` до {expiry}\n"

    bot.send_message(
        message.chat.id,
        text,
        parse_mode='Markdown',
        reply_markup=back_menu()
    )


# ========== КОМАНДА GETKEYINFO ==========
@bot.message_handler(commands=['getkeyinfo'])
def get_key_info(message):
    try:
        parts = message.text.split()
        if len(parts) < 2:
            bot.reply_to(message, "❌ Используйте: /getkeyinfo КЛЮЧ")
            return

        key = parts[1]

        conn = get_db()
        cursor = conn.cursor()
        cursor.execute(
            'SELECT key_value, created_at, expiry_date, is_paid, payment_time FROM vpn_keys WHERE key_value = ?',
            (key,)
        )
        data = cursor.fetchone()
        conn.close()

        if not data:
            bot.reply_to(message, "❌ Ключ не найден")
            return

        msg = f"🔑 **Информация о ключе**\n\n`{data['key_value']}`\n\n"
        msg += f"📅 **Создан:** {format_datetime(datetime.fromisoformat(data['created_at']))}\n"

        if data['is_paid']:
            msg += f"✅ **Оплачен:** {format_datetime(datetime.fromisoformat(data['payment_time']))}\n"
        else:
            msg += f"⏳ **Статус:** Ожидает оплаты\n"

        expiry = datetime.fromisoformat(data['expiry_date'])
        msg += f"📆 **Действует до:** {format_datetime(expiry)}\n"

        if data['is_paid']:
            now = datetime.now()
            if now < expiry:
                remaining = expiry - now
                days = remaining.days
                hours = remaining.seconds // 3600
                minutes = (remaining.seconds % 3600) // 60
                msg += f"⏱ **Осталось:** {days}д {hours}ч {minutes}мин\n"

        bot.reply_to(message, msg, parse_mode='Markdown', reply_markup=back_menu())

    except Exception as e:
        bot.reply_to(message, f"❌ Ошибка: {e}")


# ========== ЗАПУСК ==========
if __name__ == "__main__":
    print("=" * 60)
    print("🤖 VPN CONNECTING BOT (С АВТОДОБАВЛЕНИЕМ В XRAY)")
    print("=" * 60)
    print(f"💰 Цена: {PRICE_USDT} USDT")
    print(f"👤 Админ ID: {ADMIN_ID}")
    print(f"🤖 Бот: @{BOT_USERNAME}")
    print(f"🔑 Токен CryptoBot: {CRYPTO_API_TOKEN[:10]}...")
    print("✅ Запуск...")
    print("=" * 60)
    print("🔐 Админ-панель: /adminpanel")
    print("=" * 60)

    bot.infinity_polling()