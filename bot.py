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
ADMIN_ID = 1684751552
SUPPORT_GROUP_ID = -1003839964720
CRYPTO_API_TOKEN = "540507:AAyXFAZkerRA5kUrrlOmNHs1mV4xZuBZKeO"
BOT_USERNAME = "vpnconnecting_bot"

XRAY_API_URL = "http://95.81.102.13:5001/add_client"
XRAY_CHECK_URL = "http://95.81.102.13:5001/check_device"

# ========== ТАРИФЫ И ЦЕНЫ ==========
PLANS = {
    "30days": {"days": 30, "price_rub": 100, "price_usdt": 1.50, "name": "📅 1 месяц"},
    "90days": {"days": 90, "price_rub": 250, "price_usdt": 3.30, "name": "📅 3 месяца"},
    "180days": {"days": 180, "price_rub": 500, "price_usdt": 6.50, "name": "📅 6 месяцев"},
    "365days": {"days": 365, "price_rub": 1000, "price_usdt": 13.00, "name": "📅 12 месяцев"}
}

YOOKASSA_SHOP_ID = ""
YOOKASSA_SECRET_KEY = ""

def add_client_to_xray(client_id, email):
    try:
        response = requests.post(XRAY_API_URL, 
                                json={'client_id': client_id, 'email': email},
                                timeout=5)
        result = response.json()
        if result.get('success'):
            print(f"✅ Клиент {client_id} добавлен в Xray через API")
            return True
        else:
            print(f"❌ Ошибка API: {result.get('error')}")
            return False
    except Exception as e:
        print(f"❌ Ошибка соединения с API: {e}")
        return False

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
        full_link TEXT,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        expiry_date DATETIME,
        is_paid BOOLEAN DEFAULT 0,
        payment_time DATETIME,
        telegram_id TEXT,
        invoice_id TEXT UNIQUE,
        is_free BOOLEAN DEFAULT 0,
        device_id TEXT,
        plan_name TEXT,
        blocked BOOLEAN DEFAULT 0
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

def main_menu():
    keyboard = InlineKeyboardMarkup(row_width=1)
    keyboard.add(
        InlineKeyboardButton("💰 Купить VPN", callback_data="plans_menu"),
        InlineKeyboardButton("🎁 Бесплатный ключ 3 дня", callback_data="get_free_key"),
        InlineKeyboardButton("🔑 Мои ключи", callback_data="my_keys"),
        InlineKeyboardButton("🆘 Техподдержка", callback_data="support"),
        InlineKeyboardButton("❓ Помощь", callback_data="help")
    )
    return keyboard

def plans_menu():
    keyboard = InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        InlineKeyboardButton("📅 1 месяц - 100₽", callback_data="plan_30days"),
        InlineKeyboardButton("📅 3 месяца - 250₽", callback_data="plan_90days"),
        InlineKeyboardButton("📅 6 месяцев - 500₽", callback_data="plan_180days"),
        InlineKeyboardButton("📅 12 месяцев - 1000₽", callback_data="plan_365days"),
        InlineKeyboardButton("🔙 Назад", callback_data="main_menu")
    )
    return keyboard

def payment_methods_menu(plan_id, plan):
    keyboard = InlineKeyboardMarkup(row_width=1)
    if plan["price_usdt"] > 0:
        keyboard.add(InlineKeyboardButton("💳 Криптобот (USDT)", callback_data=f"pay_crypto_{plan_id}"))
    if plan["price_rub"] > 0 and YOOKASSA_SHOP_ID:
        keyboard.add(InlineKeyboardButton("🏦 ЮKassa (рубли)", callback_data=f"pay_yookassa_{plan_id}"))
    keyboard.add(InlineKeyboardButton("🔙 Назад к тарифам", callback_data="plans_menu"))
    return keyboard

def admin_menu():
    keyboard = InlineKeyboardMarkup(row_width=1)
    keyboard.add(
        InlineKeyboardButton("🎁 Бесплатный ключ", callback_data="admin_free_key"),
        InlineKeyboardButton("📊 Статистика", callback_data="admin_stats"),
        InlineKeyboardButton("📨 Ответить пользователю", callback_data="admin_reply"),
        InlineKeyboardButton("🔙 Закрыть", callback_data="main_menu")
    )
    return keyboard

def back_menu():
    keyboard = InlineKeyboardMarkup()
    keyboard.add(InlineKeyboardButton("🏠 Главное меню", callback_data="main_menu"))
    return keyboard

def confirm_menu():
    keyboard = InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        InlineKeyboardButton("✅ Принимаю", callback_data="accept_rules"),
        InlineKeyboardButton("❌ Отмена", callback_data="main_menu")
    )
    return keyboard

@bot.message_handler(commands=['start'])
def start(message):
    if message.chat.id == SUPPORT_GROUP_ID:
        return
    bot.send_message(message.chat.id,
        "🔐 **VPN CONNECTING**\n\n"
        "⚡️ Высокоскоростной VPN\n"
        "📱 1 ключ = 1 устройство\n"
        "💰 Разные тарифы на любой срок\n\n"
        "Выберите действие:",
        parse_mode='Markdown', reply_markup=main_menu())

@bot.message_handler(commands=['adminpanel'])
def admin_panel(message):
    if message.from_user.id != ADMIN_ID:
        bot.reply_to(message, "❌ Нет доступа")
        return
    bot.send_message(message.chat.id, "🔐 **АДМИН-ПАНЕЛЬ**", parse_mode='Markdown', reply_markup=admin_menu())

@bot.message_handler(func=lambda message: True)
def handle_support_message(message):
    if message.text and message.text.startswith('/'):
        return
    if message.chat.type == 'private':
        bot.forward_message(SUPPORT_GROUP_ID, message.chat.id, message.message_id)
        user_info = f"🆔 **ID:** {message.from_user.id}\n"
        user_info += f"👤 **Имя:** {message.from_user.first_name}\n"
        if message.from_user.username:
            user_info += f"📱 **Username:** @{message.from_user.username}\n"
        user_info += f"📝 **Сообщение:** {message.text}"
        bot.send_message(SUPPORT_GROUP_ID, user_info, parse_mode='Markdown')
        bot.reply_to(message, "✅ Ваше сообщение отправлено в техподдержку. Ожидайте ответа.")

# ========== ИСПРАВЛЕННАЯ КОМАНДА /reply ==========
@bot.message_handler(commands=['reply'])
def admin_reply(message):
    # Проверяем, что сообщение из группы поддержки
    if message.chat.id != SUPPORT_GROUP_ID:
        bot.reply_to(message, "❌ Эта команда работает только в группе поддержки")
        return
    
    # Проверяем, что отправитель - админ
    if message.from_user.id != ADMIN_ID:
        bot.reply_to(message, "❌ У вас нет прав администратора")
        return
    
    try:
        # Разбираем сообщение: /reply 123456789 Текст сообщения
        parts = message.text.split(maxsplit=2)
        
        if len(parts) < 3:
            bot.reply_to(message, 
                        "❌ **Неправильный формат!**\n\n"
                        "Используйте: `/reply USER_ID ТЕКСТ`\n"
                        "Например: `/reply 123456789 Ваш ключ активирован`", 
                        parse_mode='Markdown')
            return
        
        # Получаем ID пользователя и текст ответа
        user_id_str = parts[1]
        reply_text = parts[2]
        
        # Проверяем, что ID состоит только из цифр
        if not user_id_str.isdigit():
            bot.reply_to(message, "❌ USER_ID должен быть числом")
            return
        
        user_id = int(user_id_str)
        
        # Отправляем ответ пользователю
        sent_message = bot.send_message(user_id, 
                        f"📨 **Ответ от поддержки:**\n\n{reply_text}\n\n"
                        f"_Если у вас остались вопросы, напишите снова._", 
                        parse_mode='Markdown')
        
        # Проверяем, отправилось ли сообщение
        if sent_message:
            # Подтверждение админу в группу
            bot.reply_to(message, f"✅ **Ответ отправлен** пользователю `{user_id}`", parse_mode='Markdown')
        else:
            bot.reply_to(message, f"❌ Не удалось отправить сообщение пользователю `{user_id}`. Возможно, он заблокировал бота.", parse_mode='Markdown')
        
    except Exception as e:
        bot.reply_to(message, f"❌ **Ошибка:** {str(e)}", parse_mode='Markdown')

@bot.message_handler(commands=['support'])
def support_command(message):
    if message.chat.id == SUPPORT_GROUP_ID:
        return
    bot.reply_to(message, 
                "🆘 **Техподдержка**\n\n"
                "Напишите ваш вопрос, и мы ответим в ближайшее время.",
                parse_mode='Markdown')

@bot.callback_query_handler(func=lambda call: True)
def handle_callback(call):
    user_id = call.from_user.id
    data = call.data

    if data == "main_menu":
        bot.edit_message_text("🔐 VPN CONNECTING", 
                             chat_id=call.message.chat.id,
                             message_id=call.message.message_id, 
                             reply_markup=main_menu())
        bot.answer_callback_query(call.id)

    elif data == "plans_menu":
        bot.edit_message_text("📋 **Выберите тариф:**", 
                             chat_id=call.message.chat.id,
                             message_id=call.message.message_id,
                             parse_mode='Markdown',
                             reply_markup=plans_menu())
        bot.answer_callback_query(call.id)

    elif data == "help":
        bot.edit_message_text("❓ **Помощь**\n\n"
                              "1. Выберите тариф\n"
                              "2. Оплатите удобным способом\n"
                              "3. Получите ключ\n"
                              "4. 1 ключ = 1 устройство\n"
                              "5. При подключении на другое устройство ключ блокируется",
                             chat_id=call.message.chat.id,
                             message_id=call.message.message_id,
                             parse_mode='Markdown',
                             reply_markup=back_menu())
        bot.answer_callback_query(call.id)

    elif data == "support":
        bot.edit_message_text("🆘 **Техподдержка**\n\n"
                              "Напишите ваш вопрос в чат, и мы ответим.",
                             chat_id=call.message.chat.id,
                             message_id=call.message.message_id,
                             parse_mode='Markdown',
                             reply_markup=back_menu())
        bot.answer_callback_query(call.id)

    elif data == "get_free_key":
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute('''
        SELECT COUNT(*) FROM vpn_keys 
        WHERE telegram_id = ? AND is_free = 1 AND plan_name = 'free_3days'
        ''', (str(user_id),))
        free_count = cursor.fetchone()[0]
        
        if free_count > 0:
            bot.edit_message_text("❌ **Вы уже получали бесплатный ключ!**\n\n"
                                  "Бесплатный ключ выдается только один раз.",
                                 chat_id=call.message.chat.id,
                                 message_id=call.message.message_id,
                                 parse_mode='Markdown',
                                 reply_markup=main_menu())
            bot.answer_callback_query(call.id, "Уже получали")
            conn.close()
            return
        
        client_id, key = generate_key()
        expiry = datetime.now() + timedelta(days=3)
        link = f"vless://{client_id}@{SERVER_IP}:{SERVER_PORT}?security=none&type=tcp#{key}"
        
        cursor.execute('''
        INSERT INTO vpn_keys (key_value, client_id, full_link, expiry_date, telegram_id, is_paid, is_free, plan_name)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (key, client_id, link, expiry.isoformat(), str(user_id), 1, 1, "free_3days"))
        conn.commit()
        conn.close()
        
        add_client_to_xray(client_id, f"free_3days_{key}")
        
        bot.edit_message_text(f"✅ **Ваш бесплатный ключ на 3 дня:**\n\n"
                              f"🔗 `{link}`\n\n"
                              f"📅 Действует до: {format_datetime(expiry)}",
                             chat_id=call.message.chat.id,
                             message_id=call.message.message_id,
                             parse_mode='Markdown',
                             reply_markup=main_menu())
        bot.answer_callback_query(call.id, "Ключ создан!")

    elif data.startswith("plan_"):
        plan_id = data.replace("plan_", "")
        if plan_id in PLANS:
            # СТАРЫЙ БОЛЬШОЙ ТЕКСТ ПРЕДУПРЕЖДЕНИЯ
            bot.edit_message_text("⚠️ **ПРАВИЛА ИСПОЛЬЗОВАНИЯ**\n\n"
                                  "❗️ Вы берете на себя всю ответственность за использование данного VPN.\n\n"
                                  "• Разработчик бота и сервиса не несет ответственности за ваши действия\n"
                                  "• Использование VPN может регулироваться законодательством вашей страны\n"
                                  "• Вы обязуетесь соблюдать все применимые законы\n\n"
                                  "Продолжая, вы подтверждаете согласие с данными условиями.",
                                 chat_id=call.message.chat.id,
                                 message_id=call.message.message_id,
                                 parse_mode='Markdown',
                                 reply_markup=confirm_menu())
            # Сохраняем выбранный план для использования после подтверждения
            # Временно сохраняем в данных колбэка
            call.data = f"confirm_plan_{plan_id}"
            bot.answer_callback_query(call.id)

    elif data.startswith("confirm_plan_"):
        plan_id = data.replace("confirm_plan_", "")
        if plan_id in PLANS:
            plan = PLANS[plan_id]
            # Показываем способы оплаты
            bot.edit_message_text(f"💳 **{plan['name']}**\n\n"
                                  f"💰 Цена: {plan['price_rub']}₽ / {plan['price_usdt']} USDT\n\n"
                                  f"Выберите способ оплаты:",
                                 chat_id=call.message.chat.id,
                                 message_id=call.message.message_id,
                                 parse_mode='Markdown',
                                 reply_markup=payment_methods_menu(plan_id, plan))
            bot.answer_callback_query(call.id)

    elif data == "accept_rules":
        # Это больше не нужно, так как мы используем confirm_plan_
        bot.answer_callback_query(call.id)

    elif data.startswith("pay_crypto_"):
        plan_id = data.replace("pay_crypto_", "")
        plan = PLANS[plan_id]
        
        client_id, key = generate_key()
        expiry = datetime.now() + timedelta(days=plan["days"])
        link = f"vless://{client_id}@{SERVER_IP}:{SERVER_PORT}?security=none&type=tcp#{key}"
        
        invoice_id, pay_url = create_crypto_invoice(plan["price_usdt"], f"{plan['name']} ключ {key}")
        
        if not invoice_id:
            bot.answer_callback_query(call.id, "Ошибка создания счета", show_alert=True)
            return
        
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute('''
        INSERT INTO vpn_keys (key_value, client_id, full_link, expiry_date, telegram_id, is_paid, plan_name, invoice_id)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (key, client_id, link, expiry.isoformat(), str(user_id), 0, plan_id, invoice_id))
        conn.commit()
        conn.close()
        
        orders[user_id] = {'key': key, 'invoice_id': invoice_id, 'plan_id': plan_id}
        
        bot.edit_message_text(f"💳 **Оплата {plan['name']}**\n\n"
                              f"🔑 Ключ: `{key}`\n"
                              f"💰 Сумма: {plan['price_usdt']} USDT\n\n"
                              f"1. Нажмите кнопку оплаты\n"
                              f"2. Оплатите в CryptoBot\n"
                              f"3. Нажмите 'Проверить оплату'",
                             chat_id=call.message.chat.id,
                             message_id=call.message.message_id,
                             parse_mode='Markdown',
                             reply_markup=payment_menu(key, pay_url))
        bot.answer_callback_query(call.id)

    elif data.startswith("pay_yookassa_"):
        bot.answer_callback_query(call.id, "ЮKassa будет добавлена позже", show_alert=True)

    elif data.startswith("check_payment_"):
        key = data.replace("check_payment_", "")
        
        if user_id not in orders or orders[user_id]['key'] != key:
            bot.answer_callback_query(call.id, "Заказ не найден", show_alert=True)
            return
        
        if check_invoice_status(orders[user_id]['invoice_id']):
            conn = get_db()
            cursor = conn.cursor()
            cursor.execute('''
            UPDATE vpn_keys SET is_paid = 1, payment_time = ? WHERE key_value = ?
            ''', (datetime.now().isoformat(), key))
            conn.commit()
            
            cursor.execute('SELECT full_link, expiry_date FROM vpn_keys WHERE key_value = ?', (key,))
            data = cursor.fetchone()
            conn.close()
            
            if data:
                client_id = key
                add_client_to_xray(client_id, f"paid_{key}")
                
                bot.send_message(user_id,
                               f"✅ **ОПЛАЧЕНО!**\n\n"
                               f"🔗 `{data['full_link']}`\n\n"
                               f"📅 Действует до: {format_datetime(datetime.fromisoformat(data['expiry_date']))}",
                               parse_mode='Markdown', reply_markup=main_menu())
            
            if user_id in orders:
                del orders[user_id]
            
            bot.edit_message_text("✅ Платеж подтвержден!", 
                                 chat_id=call.message.chat.id,
                                 message_id=call.message.message_id, 
                                 reply_markup=main_menu())
            bot.answer_callback_query(call.id, "Ключ активирован!")
        else:
            bot.answer_callback_query(call.id, "❌ Платеж не найден", show_alert=True)

    elif data == "my_keys":
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute('''
        SELECT full_link, expiry_date, is_paid, plan_name, device_id, blocked 
        FROM vpn_keys WHERE telegram_id = ? ORDER BY created_at DESC
        ''', (str(user_id),))
        keys = cursor.fetchall()
        conn.close()
        
        if not keys:
            text = "🔑 **Ваши ключи**\n\nУ вас пока нет ключей."
        else:
            text = "🔑 **Ваши ключи**\n\n"
            for k in keys:
                if k['blocked']:
                    status = "❌ ЗАБЛОКИРОВАН"
                elif k['is_paid']:
                    status = "✅"
                else:
                    status = "⏳"
                
                if k['device_id'] and not k['blocked']:
                    status += f" 📱 (устр: {k['device_id'][:8]}...)"
                
                expiry = datetime.fromisoformat(k['expiry_date']).strftime('%d.%m.%Y')
                plan_name = PLANS.get(k['plan_name'], {}).get('name', 'VPN') if k['plan_name'] else 'VPN'
                
                text += f"{status} **{plan_name}**\n"
                text += f"🔗 `{k['full_link']}`\n"
                text += f"📅 до {expiry}\n\n"
        
        bot.edit_message_text(text, 
                             chat_id=call.message.chat.id,
                             message_id=call.message.message_id,
                             parse_mode='Markdown',
                             reply_markup=back_menu())
        bot.answer_callback_query(call.id)

    elif data == "admin_free_key":
        if user_id != ADMIN_ID:
            bot.answer_callback_query(call.id, "❌ Доступ запрещен", show_alert=True)
            return
        
        client_id, key = generate_key()
        expiry = datetime.now() + timedelta(days=30)
        link = f"vless://{client_id}@{SERVER_IP}:{SERVER_PORT}?security=none&type=tcp#{key}"
        
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute('''
        INSERT INTO vpn_keys (key_value, client_id, full_link, expiry_date, telegram_id, is_paid, is_free)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (key, client_id, link, expiry.isoformat(), str(user_id), 1, 1))
        conn.commit()
        conn.close()
        
        add_client_to_xray(client_id, f"admin_free_{key}")
        
        bot.edit_message_text(f"✅ **Бесплатный ключ:**\n\n🔗 `{link}`", 
                             chat_id=call.message.chat.id,
                             message_id=call.message.message_id,
                             parse_mode='Markdown',
                             reply_markup=admin_menu())
        bot.answer_callback_query(call.id, "Ключ создан!")

    elif data == "admin_stats":
        if user_id != ADMIN_ID:
            bot.answer_callback_query(call.id, "❌ Доступ запрещен", show_alert=True)
            return
        
        conn = get_db()
        cursor = conn.cursor()
        total = cursor.execute('SELECT COUNT(*) FROM vpn_keys').fetchone()[0]
        paid = cursor.execute('SELECT COUNT(*) FROM vpn_keys WHERE is_paid = 1').fetchone()[0]
        free = cursor.execute('SELECT COUNT(*) FROM vpn_keys WHERE is_free = 1').fetchone()[0]
        active = cursor.execute('SELECT COUNT(*) FROM vpn_keys WHERE is_paid = 1 AND datetime(expiry_date) > datetime("now")').fetchone()[0]
        blocked = cursor.execute('SELECT COUNT(*) FROM vpn_keys WHERE blocked = 1').fetchone()[0]
        conn.close()
        
        bot.edit_message_text(f"📊 **СТАТИСТИКА**\n\n"
                              f"🔑 Всего ключей: {total}\n"
                              f"✅ Оплаченных: {paid}\n"
                              f"🎁 Бесплатных: {free}\n"
                              f"⚡️ Активных: {active}\n"
                              f"❌ Заблокировано: {blocked}",
                             chat_id=call.message.chat.id,
                             message_id=call.message.message_id,
                             parse_mode='Markdown',
                             reply_markup=admin_menu())
        bot.answer_callback_query(call.id)

    elif data == "admin_reply":
        if user_id != ADMIN_ID:
            bot.answer_callback_query(call.id, "❌ Доступ запрещен", show_alert=True)
            return
        
        bot.edit_message_text("📨 **Ответ пользователю**\n\n"
                              "Используйте команду:\n"
                              "`/reply USER_ID ТЕКСТ`\n\n"
                              "Например: `/reply 123456789 Ваш ключ активирован`",
                             chat_id=call.message.chat.id,
                             message_id=call.message.message_id,
                             parse_mode='Markdown',
                             reply_markup=admin_menu())
        bot.answer_callback_query(call.id)

    elif data == "cancel_order":
        if user_id in orders:
            key = orders[user_id]['key']
            conn = get_db()
            cursor = conn.cursor()
            cursor.execute('DELETE FROM vpn_keys WHERE key_value = ? AND is_paid = 0', (key,))
            conn.commit()
            conn.close()
            del orders[user_id]
        bot.edit_message_text("❌ Заказ отменен", 
                             chat_id=call.message.chat.id,
                             message_id=call.message.message_id, 
                             reply_markup=main_menu())
        bot.answer_callback_query(call.id)

def payment_menu(key, pay_url):
    keyboard = InlineKeyboardMarkup(row_width=1)
    keyboard.add(
        InlineKeyboardButton("💳 Оплатить", url=pay_url),
        InlineKeyboardButton("✅ Проверить оплату", callback_data=f"check_payment_{key}"),
        InlineKeyboardButton("❌ Отменить", callback_data="cancel_order"),
        InlineKeyboardButton("🏠 Главное меню", callback_data="main_menu")
    )
    return keyboard

@bot.message_handler(commands=['mykeys'])
def my_keys(message):
    user_id = message.from_user.id
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
    SELECT full_link, expiry_date, is_paid, plan_name, device_id, blocked 
    FROM vpn_keys WHERE telegram_id = ? ORDER BY created_at DESC
    ''', (str(user_id),))
    keys = cursor.fetchall()
    conn.close()
    
    if not keys:
        text = "🔑 **Ваши ключи**\n\nУ вас пока нет ключей."
    else:
        text = "🔑 **Ваши ключи**\n\n"
        for k in keys:
            if k['blocked']:
                status = "❌ ЗАБЛОКИРОВАН"
            elif k['is_paid']:
                status = "✅"
            else:
                status = "⏳"
            
            if k['device_id'] and not k['blocked']:
                status += f" 📱 (устр: {k['device_id'][:8]}...)"
            
            expiry = datetime.fromisoformat(k['expiry_date']).strftime('%d.%m.%Y')
            plan_name = PLANS.get(k['plan_name'], {}).get('name', 'VPN') if k['plan_name'] else 'VPN'
            
            text += f"{status} **{plan_name}**\n"
            text += f"🔗 `{k['full_link']}`\n"
            text += f"📅 до {expiry}\n\n"
    
    bot.send_message(message.chat.id, text, parse_mode='Markdown', reply_markup=back_menu())

@bot.message_handler(commands=['getkeyinfo'])
def get_key_info(message):
    try:
        key = message.text.split()[1]
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute('''
        SELECT key_value, full_link, created_at, expiry_date, is_paid, payment_time, plan_name, device_id, blocked 
        FROM vpn_keys WHERE key_value = ?
        ''', (key,))
        data = cursor.fetchone()
        conn.close()
        
        if not data:
            bot.reply_to(message, "❌ Ключ не найден")
            return
        
        msg = f"🔑 **Информация о ключе**\n\n"
        msg += f"🔗 `{data['full_link']}`\n\n"
        msg += f"📅 **Создан:** {format_datetime(datetime.fromisoformat(data['created_at']))}\n"
        msg += f"📆 **Действует до:** {format_datetime(datetime.fromisoformat(data['expiry_date']))}\n"
        
        if data['blocked']:
            msg += f"❌ **Статус:** ЗАБЛОКИРОВАН\n"
        elif data['is_paid']:
            msg += f"✅ **Оплачен:** {format_datetime(datetime.fromisoformat(data['payment_time']))}\n"
        else:
            msg += f"⏳ **Статус:** Ожидает оплаты\n"
        
        if data['plan_name']:
            plan_name = PLANS.get(data['plan_name'], {}).get('name', data['plan_name'])
            msg += f"📋 **Тариф:** {plan_name}\n"
        
        if data['device_id']:
            msg += f"📱 **Привязан к устройству:** `{data['device_id']}`\n"
        
        bot.reply_to(message, msg, parse_mode='Markdown', reply_markup=back_menu())
    except:
        bot.reply_to(message, "❌ Используйте: /getkeyinfo КЛЮЧ")

if __name__ == "__main__":
    print("=" * 60)
    print("🤖 VPN БОТ (1,3,6,12 МЕСЯЦЕВ)")
    print("=" * 60)
    print(f"👤 Админ ID: {ADMIN_ID}")
    print(f"👥 Группа поддержки: {SUPPORT_GROUP_ID}")
    print(f"🤖 Бот: @{BOT_USERNAME}")
    print("✅ Запуск...")
    print("=" * 60)
    bot.infinity_polling()
