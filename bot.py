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

SERVER_IP = "95.81.102.13"
SERVER_PORT = 443
PRICE_USDT = 1.50
ORDER_LIFETIME = 10
ADMIN_ID = 1684751552
CRYPTO_API_TOKEN = "540507:AAyXFAZkerRA5kUrrlOmNHs1mV4xZuBZKeO"
BOT_USERNAME = "vpnconnecting_bot"


# ========== ПРОСТАЯ ФУНКЦИЯ ДОБАВЛЕНИЯ В XRAY ==========
def add_client_to_xray(client_id, email):
    try:
        with open('/usr/local/etc/xray/config.json', 'r') as f:
            config = json.load(f)

        config['inbounds'][0]['settings']['clients'].append({
            "id": client_id,
            "email": email,
            "level": 0
        })

        with open('/usr/local/etc/xray/config.json', 'w') as f:
            json.dump(config, f, indent=2)

        subprocess.run(['systemctl', 'restart', 'xray'])
        print(f"✅ Ключ добавлен в XRAY")
        return True
    except Exception as e:
        print(f"❌ Ошибка: {e}")
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
        invoice_id TEXT UNIQUE
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
            return result["result"]["invoice_id"], result["result"]["pay_url"]
        return None, None
    except:
        return None, None


def check_invoice_status(invoice_id):
    try:
        url = "https://pay.crypt.bot/api/getInvoices"
        headers = {"Crypto-Pay-API-Token": CRYPTO_API_TOKEN}
        params = {"invoice_ids": invoice_id}
        response = requests.get(url, headers=headers, params=params)
        result = response.json()
        if result.get("ok") and result["result"]["items"]:
            return result["result"]["items"][0]["status"] == "paid"
        return False
    except:
        return False


# ========== КНОПКИ ==========
def main_menu():
    keyboard = InlineKeyboardMarkup(row_width=1)
    keyboard.add(
        InlineKeyboardButton("💰 Купить VPN", callback_data="buy_vpn"),
        InlineKeyboardButton("🔑 Мои ключи", callback_data="my_keys"),
        InlineKeyboardButton("❓ Помощь", callback_data="help")
    )
    return keyboard


def admin_menu():
    keyboard = InlineKeyboardMarkup(row_width=1)
    keyboard.add(
        InlineKeyboardButton("🎁 Бесплатный ключ", callback_data="admin_free_key"),
        InlineKeyboardButton("📊 Статистика", callback_data="admin_stats"),
        InlineKeyboardButton("🔙 Закрыть", callback_data="main_menu")
    )
    return keyboard


def confirm_menu():
    keyboard = InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        InlineKeyboardButton("✅ Принимаю", callback_data="accept_rules"),
        InlineKeyboardButton("❌ Отмена", callback_data="main_menu")
    )
    return keyboard


def payment_menu(key, pay_url):
    keyboard = InlineKeyboardMarkup(row_width=1)
    keyboard.add(
        InlineKeyboardButton("💳 Оплатить 1.5 USDT", url=pay_url),
        InlineKeyboardButton("✅ Я оплатил", callback_data=f"check_payment_{key}"),
        InlineKeyboardButton("❌ Отменить", callback_data="cancel_order"),
        InlineKeyboardButton("🏠 Меню", callback_data="main_menu")
    )
    return keyboard


def back_menu():
    keyboard = InlineKeyboardMarkup()
    keyboard.add(InlineKeyboardButton("🏠 Меню", callback_data="main_menu"))
    return keyboard


# ========== КОМАНДЫ ==========
@bot.message_handler(commands=['start'])
def start(message):
    bot.send_message(message.chat.id,
                     "🔐 **VPN CONNECTING**\n\n⚡️ Высокоскоростной VPN\n📱 1 ключ = 1 устройство\n📅 30 дней\n\n💰 Цена: 1.5 USDT",
                     parse_mode='Markdown', reply_markup=main_menu())


@bot.message_handler(commands=['adminpanel'])
def admin_panel(message):
    if message.from_user.id != ADMIN_ID:
        bot.reply_to(message, "❌ Нет доступа")
        return
    bot.send_message(message.chat.id, "🔐 **АДМИН-ПАНЕЛЬ**", parse_mode='Markdown', reply_markup=admin_menu())


@bot.callback_query_handler(func=lambda call: True)
def handle_callback(call):
    user_id = call.from_user.id
    data = call.data

    if data == "main_menu":
        bot.edit_message_text("🔐 VPN CONNECTING", chat_id=call.message.chat.id,
                              message_id=call.message.message_id, reply_markup=main_menu())
        bot.answer_callback_query(call.id)

    elif data == "help":
        bot.edit_message_text("❓ Помощь", chat_id=call.message.chat.id,
                              message_id=call.message.message_id, reply_markup=back_menu())
        bot.answer_callback_query(call.id)

    elif data == "my_keys":
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute('SELECT key_value, expiry_date, is_paid FROM vpn_keys WHERE telegram_id = ?', (str(user_id),))
        keys = cursor.fetchall()
        conn.close()
        if not keys:
            text = "🔑 **Ваши ключи**\n\nУ вас пока нет ключей."
        else:
            text = "🔑 **Ваши ключи**\n\n"
            for k in keys:
                status = "✅" if k['is_paid'] else "⏳"
                expiry = datetime.fromisoformat(k['expiry_date']).strftime('%d.%m.%Y')
                text += f"{status} `{k['key_value']}` до {expiry}\n"
        bot.edit_message_text(text, chat_id=call.message.chat.id, message_id=call.message.message_id,
                              parse_mode='Markdown', reply_markup=back_menu())
        bot.answer_callback_query(call.id)

    elif data == "admin_free_key":
        if user_id != ADMIN_ID:
            bot.answer_callback_query(call.id, "❌ Доступ запрещен", show_alert=True)
            return
        client_id, key = generate_key()
        expiry = datetime.now() + timedelta(days=30)
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute(
            'INSERT INTO vpn_keys (key_value, client_id, expiry_date, telegram_id, is_paid) VALUES (?, ?, ?, ?, ?)',
            (key, client_id, expiry.isoformat(), str(user_id), 1))
        conn.commit()
        conn.close()
        add_client_to_xray(client_id, f"admin_{key}")
        link = f"vless://{client_id}@{SERVER_IP}:{SERVER_PORT}?security=none&type=tcp&headerType=http&host=www.google.com#{key}"
        bot.edit_message_text(f"✅ **Ключ:** `{key}`\n🔗 `{link}`", chat_id=call.message.chat.id,
                              message_id=call.message.message_id, parse_mode='Markdown', reply_markup=admin_menu())
        bot.answer_callback_query(call.id, "Ключ создан!")

    elif data == "admin_stats":
        if user_id != ADMIN_ID:
            bot.answer_callback_query(call.id, "❌ Доступ запрещен", show_alert=True)
            return
        conn = get_db()
        cursor = conn.cursor()
        total = cursor.execute('SELECT COUNT(*) FROM vpn_keys').fetchone()[0]
        paid = cursor.execute('SELECT COUNT(*) FROM vpn_keys WHERE is_paid = 1').fetchone()[0]
        conn.close()
        bot.edit_message_text(f"📊 **Статистика**\n\n🔑 Всего: {total}\n✅ Оплаченных: {paid}",
                              chat_id=call.message.chat.id, message_id=call.message.message_id,
                              parse_mode='Markdown', reply_markup=admin_menu())
        bot.answer_callback_query(call.id)

    elif data == "buy_vpn":
        if user_id in orders:
            bot.answer_callback_query(call.id, "У вас уже есть заказ", show_alert=True)
            return
        bot.edit_message_text("⚠️ **ПРАВИЛА**\n\nПродолжая, вы соглашаетесь с условиями.",
                              chat_id=call.message.chat.id, message_id=call.message.message_id,
                              parse_mode='Markdown', reply_markup=confirm_menu())
        bot.answer_callback_query(call.id)

    elif data == "accept_rules":
        if user_id in orders:
            bot.answer_callback_query(call.id, "У вас уже есть заказ")
            return
        client_id, key = generate_key()
        expiry = datetime.now() + timedelta(days=30)
        invoice_id, pay_url = create_crypto_invoice(PRICE_USDT, f"VPN {key}")
        if not invoice_id:
            bot.answer_callback_query(call.id, "Ошибка счета", show_alert=True)
            return
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute(
            'INSERT INTO vpn_keys (key_value, client_id, expiry_date, telegram_id, is_paid, invoice_id) VALUES (?, ?, ?, ?, ?, ?)',
            (key, client_id, expiry.isoformat(), str(user_id), 0, invoice_id))
        conn.commit()
        conn.close()
        orders[user_id] = {'key': key, 'invoice_id': invoice_id}
        bot.edit_message_text(f"✅ **Ключ:** `{key}`\n💰 Сумма: {PRICE_USDT} USDT",
                              chat_id=call.message.chat.id, message_id=call.message.message_id,
                              parse_mode='Markdown', reply_markup=payment_menu(key, pay_url))
        bot.answer_callback_query(call.id)

    elif data.startswith("check_payment_"):
        key = data.replace("check_payment_", "")
        if user_id not in orders or orders[user_id]['key'] != key:
            bot.answer_callback_query(call.id, "Заказ не найден", show_alert=True)
            return
        if check_invoice_status(orders[user_id]['invoice_id']):
            conn = get_db()
            cursor = conn.cursor()
            cursor.execute('SELECT client_id, expiry_date FROM vpn_keys WHERE key_value = ?', (key,))
            data = cursor.fetchone()
            if data:
                cursor.execute('UPDATE vpn_keys SET is_paid = 1, payment_time = ? WHERE key_value = ?',
                               (datetime.now().isoformat(), key))
                conn.commit()
                add_client_to_xray(data['client_id'], f"user_{user_id}_{key}")
                link = f"vless://{data['client_id']}@{SERVER_IP}:{SERVER_PORT}?security=none&type=tcp&headerType=http&host=www.google.com#{key}"
                bot.send_message(user_id, f"✅ **ОПЛАЧЕНО!**\n🔗 `{link}`", parse_mode='Markdown')
            conn.close()
            if user_id in orders:
                del orders[user_id]
            bot.edit_message_text("✅ Платеж подтвержден!", chat_id=call.message.chat.id,
                                  message_id=call.message.message_id, reply_markup=main_menu())
            bot.answer_callback_query(call.id, "Ключ активирован!")
        else:
            bot.answer_callback_query(call.id, "❌ Платеж не найден", show_alert=True)

    elif data == "cancel_order":
        if user_id in orders:
            key = orders[user_id]['key']
            conn = get_db()
            cursor = conn.cursor()
            cursor.execute('DELETE FROM vpn_keys WHERE key_value = ? AND is_paid = 0', (key,))
            conn.commit()
            conn.close()
            del orders[user_id]
        bot.edit_message_text("❌ Заказ отменен", chat_id=call.message.chat.id,
                              message_id=call.message.message_id, reply_markup=main_menu())
        bot.answer_callback_query(call.id)


if __name__ == "__main__":
    print("=" * 60)
    print("🤖 VPN БОТ ЗАПУЩЕН")
    print("=" * 60)
    bot.infinity_polling()