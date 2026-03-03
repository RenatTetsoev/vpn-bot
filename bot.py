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
import logging
from datetime import datetime, timedelta
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

# Настройка логирования
logging.basicConfig(
    level=logging.ERROR,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    filename='bot_errors.log'
)

TOKEN = '8632835912:AAFesJq2qhoBw4N_h5cmB-fVQauvvOwpUwQ'
bot = telebot.TeleBot(TOKEN)

# ========== НАСТРОЙКИ ==========
SERVER_IP = "95.81.102.13"
SERVER_PORT = 443
PRICE_USDT = 1.50
ORDER_LIFETIME = 10
ADMIN_ID = 1684751552
SUPPORT_GROUP_ID = -1001234567890  # ЗАМЕНИ НА СВОЙ ID ГРУППЫ!
CRYPTO_API_TOKEN = "540507:AAyXFAZkerRA5kUrrlOmNHs1mV4xZuBZKeO"
BOT_USERNAME = "vpnconnecting_bot"
XRAY_CONFIG = "/usr/local/etc/xray/config.json"


# ========== БЕЗОПАСНОЕ РЕДАКТИРОВАНИЕ СООБЩЕНИЙ ==========
def safe_edit_message(chat_id, message_id, text, reply_markup=None):
    """Безопасно редактирует сообщение без ошибки 400"""
    try:
        bot.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text=text,
            parse_mode='Markdown',
            reply_markup=reply_markup
        )
    except Exception as e:
        if "message is not modified" not in str(e):
            print(f"Ошибка: {e}")
            logging.error(f"Ошибка редактирования: {e}")


# ========== ФУНКЦИЯ ДОБАВЛЕНИЯ В XRAY ==========
def add_client_to_xray(client_id, email):
    """Добавляет клиента в конфиг Xray и перезапускает сервис"""
    try:
        print(f"🔄 Добавляю клиента {client_id[:8]}...")

        with open(XRAY_CONFIG, 'r') as f:
            config = json.load(f)

        old_count = len(config['inbounds'][0]['settings']['clients'])

        new_client = {
            "id": client_id,
            "email": email,
            "level": 0
        }

        config['inbounds'][0]['settings']['clients'].append(new_client)

        with open(XRAY_CONFIG, 'w') as f:
            json.dump(config, f, indent=2)

        print(f"✅ Клиентов было {old_count}, стало {old_count + 1}")

        subprocess.run(['pkill', 'xray'])
        subprocess.Popen(['xray', 'run', '-config', XRAY_CONFIG],
                         stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL)
        return True
    except Exception as e:
        print(f"❌ Ошибка: {e}")
        logging.error(f"Ошибка добавления в Xray: {e}")
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
        is_free BOOLEAN DEFAULT 0,
        device_id TEXT,
        last_used DATETIME
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
    keyboard.add(
        InlineKeyboardButton("💰 Купить VPN", callback_data="buy_vpn"),
        InlineKeyboardButton("🔑 Мои ключи", callback_data="my_keys"),
        InlineKeyboardButton("🆘 Техподдержка", callback_data="support"),
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


def support_menu():
    keyboard = InlineKeyboardMarkup(row_width=1)
    keyboard.add(
        InlineKeyboardButton("📝 Написать в поддержку", callback_data="write_support"),
        InlineKeyboardButton("📋 Частые вопросы", callback_data="faq"),
        InlineKeyboardButton("🔙 Назад", callback_data="main_menu")
    )
    return keyboard


# ========== ОБРАБОТЧИК КОМАНД ==========
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


# ========== ОБРАБОТЧИК КНОПОК ==========
@bot.callback_query_handler(func=lambda call: True)
def handle_callback(call):
    user_id = call.from_user.id
    data = call.data

    if data == "main_menu":
        safe_edit_message(call.message.chat.id, call.message.message_id,
                          "🔐 VPN CONNECTING", main_menu())
        bot.answer_callback_query(call.id)

    elif data == "help":
        help_text = (
            "❓ **Помощь**\n\n"
            "1. **Как купить VPN?**\n"
            "   - Нажми 'Купить VPN'\n"
            "   - Прочитай правила\n"
            "   - Оплати 1.5 USDT\n"
            "   - Нажми 'Я оплатил'\n"
            "   - Получи VLESS ссылку\n\n"
            "2. **Как подключиться?**\n"
            "   - Скачай v2rayNG\n"
            "   - Вставь VLESS ссылку\n"
            "   - Нажми подключиться\n\n"
            "3. **Сколько устройств?**\n"
            "   - 1 ключ = 1 устройство\n"
            "   - Привязка по первому подключению\n\n"
            "4. **Срок действия?**\n"
            "   - 30 дней с момента покупки\n\n"
            "5. **Проблемы?**\n"
            "   - Нажми 'Техподдержка'"
        )
        safe_edit_message(call.message.chat.id, call.message.message_id,
                          help_text, back_menu())
        bot.answer_callback_query(call.id)

    elif data == "support":
        safe_edit_message(call.message.chat.id, call.message.message_id,
                          "🆘 **Техподдержка**\n\nВыберите действие:",
                          support_menu())
        bot.answer_callback_query(call.id)

    elif data == "faq":
        faq_text = (
            "📋 **Часто задаваемые вопросы**\n\n"
            "❓ **VPN не работает?**\n"
            "   - Проверьте интернет\n"
            "   - Убедитесь что ключ оплачен\n"
            "   - Попробуйте переподключиться\n\n"
            "❓ **Не могу подключиться?**\n"
            "   - Проверьте ссылку\n"
            "   - Используйте v2rayNG\n\n"
            "❓ **Ключ истек?**\n"
            "   - Купите новый ключ\n\n"
            "❓ **Деньги списали, а ключ не пришел?**\n"
            "   - Напишите в поддержку с номером транзакции"
        )
        safe_edit_message(call.message.chat.id, call.message.message_id,
                          faq_text, support_menu())
        bot.answer_callback_query(call.id)

    elif data == "write_support":
        safe_edit_message(
            call.message.chat.id, call.message.message_id,
            "📝 **Написать в поддержку**\n\n"
            "Напишите ваш вопрос в ответ на это сообщение.\n"
            "Администратор ответит вам в ближайшее время."
        )
        bot.register_next_step_handler_by_chat_id(call.message.chat.id, forward_to_support)
        bot.answer_callback_query(call.id)

    elif data == "my_keys":
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute('SELECT key_value, expiry_date, is_paid, device_id FROM vpn_keys WHERE telegram_id = ?',
                       (str(user_id),))
        keys = cursor.fetchall()
        conn.close()
        if not keys:
            text = "🔑 **Ваши ключи**\n\nУ вас пока нет ключей."
        else:
            text = "🔑 **Ваши ключи**\n\n"
            for k in keys:
                status = "✅" if k['is_paid'] else "⏳"
                device = f" (устр: {k['device_id'][:8]}...)" if k['device_id'] else " (не активирован)"
                expiry = datetime.fromisoformat(k['expiry_date']).strftime('%d.%m.%Y')
                text += f"{status} `{k['key_value']}`{device} до {expiry}\n"
        safe_edit_message(call.message.chat.id, call.message.message_id,
                          text, back_menu())
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
        add_client_to_xray(client_id, f"admin_{key}")
        link = f"vless://{client_id}@{SERVER_IP}:{SERVER_PORT}?security=none&type=tcp&headerType=http&host=www.google.com#{key}"
        safe_edit_message(call.message.chat.id, call.message.message_id,
                          f"✅ **Бесплатный ключ:**\n🔗 `{link}`", admin_menu())
        bot.answer_callback_query(call.id)

    elif data == "admin_stats":
        if user_id != ADMIN_ID:
            bot.answer_callback_query(call.id, "❌ Доступ запрещен", show_alert=True)
            return
        conn = get_db()
        cursor = conn.cursor()
        total = cursor.execute('SELECT COUNT(*) FROM vpn_keys').fetchone()[0]
        paid = cursor.execute('SELECT COUNT(*) FROM vpn_keys WHERE is_paid = 1').fetchone()[0]
        free = cursor.execute('SELECT COUNT(*) FROM vpn_keys WHERE is_free = 1').fetchone()[0]
        active = cursor.execute('SELECT COUNT(*) FROM vpn_keys WHERE is_paid = 1 AND device_id IS NOT NULL').fetchone()[
            0]
        conn.close()
        safe_edit_message(call.message.chat.id, call.message.message_id,
                          f"📊 **Статистика**\n\n🔑 Всего: {total}\n✅ Оплаченных: {paid}\n🎁 Бесплатных: {free}\n📱 Активных устройств: {active}",
                          admin_menu())
        bot.answer_callback_query(call.id)

    elif data == "buy_vpn":
        if user_id in orders:
            bot.answer_callback_query(call.id, "У вас уже есть заказ", show_alert=True)
            return

        rules_text = (
            "⚠️ **ПРАВИЛА ИСПОЛЬЗОВАНИЯ**\n\n"
            "❗️ **Вы берете на себя всю ответственность** за использование данного VPN.\n\n"
            "• Разработчик бота и сервиса не несет ответственности за ваши действия, "
            "совершенные с использованием VPN, а также за возможные последствия этих действий.\n\n"
            "• Использование VPN может регулироваться законодательством вашей страны. "
            "Вы обязуетесь соблюдать все применимые законы.\n\n"
            "• Сервис предоставляется строго для личного использования. "
            "Запрещено передавать ключи третьим лицам.\n\n"
            "• В случае нарушения правил, ключ может быть заблокирован без возврата средств.\n\n"
            "• Средства за оплаченные ключи не возвращаются, так как товар является цифровым.\n\n"
            "• Техническая поддержка осуществляется через кнопку 'Техподдержка'.\n\n"
            "Продолжая, вы подтверждаете, что ознакомились и согласны с данными условиями."
        )

        safe_edit_message(call.message.chat.id, call.message.message_id,
                          rules_text, confirm_menu())
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
        cursor.execute('''
        INSERT INTO vpn_keys (key_value, client_id, expiry_date, telegram_id, is_paid, invoice_id)
        VALUES (?, ?, ?, ?, ?, ?)
        ''', (key, client_id, expiry.isoformat(), str(user_id), 0, invoice_id))
        conn.commit()
        conn.close()
        orders[user_id] = {'key': key, 'invoice_id': invoice_id}
        safe_edit_message(call.message.chat.id, call.message.message_id,
                          f"✅ **Ключ:** `{key}`\n💰 Сумма: {PRICE_USDT} USDT",
                          payment_menu(key, pay_url))
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
            safe_edit_message(call.message.chat.id, call.message.message_id,
                              "✅ Платеж подтвержден!", main_menu())
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
        safe_edit_message(call.message.chat.id, call.message.message_id,
                          "❌ Заказ отменен", main_menu())
        bot.answer_callback_query(call.id)


# ========== ПЕРЕСЫЛКА В ТЕХПОДДЕРЖКУ ==========
def forward_to_support(message):
    """Пересылает сообщение пользователя в группу поддержки"""
    try:
        user_id = message.from_user.id
        user_name = message.from_user.username or message.from_user.first_name

        bot.forward_message(SUPPORT_GROUP_ID, message.chat.id, message.message_id)
        bot.send_message(
            SUPPORT_GROUP_ID,
            f"🆘 **Новый запрос в поддержку**\n"
            f"👤 Пользователь: @{user_name}\n"
            f"🆔 ID: {user_id}\n"
            f"📅 {datetime.now().strftime('%d.%m.%Y %H:%M')}",
            parse_mode='Markdown'
        )
        bot.reply_to(message, "✅ Ваш запрос отправлен в техподдержку. Ожидайте ответа.")
    except Exception as e:
        bot.reply_to(message, f"❌ Ошибка: {e}")
        logging.error(f"Ошибка поддержки: {e}")


# ========== КОМАНДА MYKEYS ==========
@bot.message_handler(commands=['mykeys'])
def my_keys(message):
    user_id = message.from_user.id
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT key_value, expiry_date, is_paid, device_id FROM vpn_keys WHERE telegram_id = ?',
                   (str(user_id),))
    keys = cursor.fetchall()
    conn.close()
    if not keys:
        text = "🔑 **Ваши ключи**\n\nУ вас пока нет ключей."
    else:
        text = "🔑 **Ваши ключи**\n\n"
        for k in keys:
            status = "✅" if k['is_paid'] else "⏳"
            device = f" (устр: {k['device_id'][:8]}...)" if k['device_id'] else " (не активирован)"
            expiry = datetime.fromisoformat(k['expiry_date']).strftime('%d.%m.%Y')
            text += f"{status} `{k['key_value']}`{device} до {expiry}\n"
    bot.send_message(message.chat.id, text, parse_mode='Markdown', reply_markup=back_menu())


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
            'SELECT key_value, created_at, expiry_date, is_paid, payment_time, device_id FROM vpn_keys WHERE key_value = ?',
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

        if data['device_id']:
            msg += f"📱 **Привязан к устройству:** `{data['device_id'][:8]}...`\n"
        else:
            msg += f"📱 **Устройство:** Не активирован\n"

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
            else:
                msg += f"⏱ **Статус:** Истек\n"

        bot.reply_to(message, msg, parse_mode='Markdown', reply_markup=back_menu())

    except Exception as e:
        bot.reply_to(message, f"❌ Ошибка: {e}")
        logging.error(f"Ошибка getkeyinfo: {e}")


if __name__ == "__main__":
    print("=" * 60)
    print("🤖 VPN БОТ С ТЕХПОДДЕРЖКОЙ")
    print("=" * 60)
    print(f"👤 Админ ID: {ADMIN_ID}")
    print(f"🆘 Группа поддержки ID: {SUPPORT_GROUP_ID}")
    print("=" * 60)
    print("✅ Бот запущен без ошибок 400")
    print("=" * 60)

    bot.infinity_polling()