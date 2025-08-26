# main.py — CurrencyBot 3.0

import os
import re
import requests
import sqlite3
import json
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters, CallbackQueryHandler, InlineQueryHandler
import matplotlib.pyplot as plt
import io

# ===================================
TOKEN = os.getenv("TOKEN")
DB_PATH = "bot.db"
# ===================================

# --- Инициализация базы данных ---
def init_db():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            lang TEXT DEFAULT 'ru',
            theme TEXT DEFAULT 'light',
            favorites TEXT DEFAULT 'USD,EUR,RUB'
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            from_curr TEXT,
            to_curr TEXT,
            amount REAL,
            result REAL,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS alerts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            currency TEXT,
            operator TEXT,
            target REAL
        )
    """)
    conn.commit()
    conn.close()

init_db()

# --- Кэш курсов ---
class CurrencyCache:
    def __init__(self):
        self.rates = {}
        self.last_update = None
        self.base = "USD"

    async def update_rates(self):
        try:
            response = requests.get(f"https://api.exchangerate-api.com/v4/latest/{self.base}")
            if response.status_code != 200:
                print("❌ Ошибка API:", response.status_code)
                return
            data = response.json()
            self.rates = data["rates"]
            self.last_update = datetime.now()
            print("✅ Курсы обновлены")
        except Exception as e:
            print("❌ Ошибка загрузки курсов:", e)

    def is_expired(self):
        return self.last_update is None or datetime.now() - self.last_update > timedelta(hours=1)

    def convert(self, amount: float, from_curr: str, to_curr: str) -> float:
        from_curr = from_curr.upper()
        to_curr = to_curr.upper()
        if from_curr == to_curr:
            return amount
        rate_from = self.rates.get(from_curr)
        rate_to = self.rates.get(to_curr)
        if not rate_from or not rate_to:
            return None
        usd_amount = amount / rate_from
        return usd_amount * rate_to

cache = CurrencyCache()

# --- Получить настройки пользователя ---
def get_user_settings(user_id):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT * FROM users WHERE user_id=?", (user_id,))
    row = cur.fetchone()
    if not row:
        cur.execute("INSERT INTO users (user_id) VALUES (?)", (user_id,))
        conn.commit()
        row = (user_id, 'ru', 'light', 'USD,EUR,RUB')
    conn.close()
    return {
        "user_id": row[0],
        "lang": row[1],
        "theme": row[2],
        "favorites": row[3].split(",") if row[3] else []
    }

# --- Сохранить настройки пользователя ---
def save_user_settings(user_id, lang=None, theme=None, favorites=None):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    fields = []
    values = []
    if lang is not None:
        fields.append("lang = ?")
        values.append(lang)
    if theme is not None:
        fields.append("theme = ?")
        values.append(theme)
    if favorites is not None:
        fields.append("favorites = ?")
        values.append(",".join(favorites))
    if fields:
        values.append(user_id)
        query = f"UPDATE users SET {', '.join(fields)} WHERE user_id = ?"
        cur.execute(query, values)
        conn.commit()
    conn.close()

# --- Добавить в историю ---
def add_history(user_id, from_curr, to_curr, amount, result):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO history (user_id, from_curr, to_curr, amount, result)
        VALUES (?, ?, ?, ?, ?)
    """, (user_id, from_curr, to_curr, amount, result))
    conn.commit()
    conn.close()

# --- Получить последние 3 записи из истории ---
def get_recent_history(user_id, limit=3):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
        SELECT from_curr, to_curr, amount, result FROM history
        WHERE user_id = ?
        ORDER BY timestamp DESC
        LIMIT ?
    """, (user_id, limit))
    rows = cur.fetchall()
    conn.close()
    return rows

# --- Получить избранные валюты ---
def get_favorites(user_id):
    settings = get_user_settings(user_id)
    return settings["favorites"]

# --- Языки ---
LANGS = {
    "ru": {
        "start": "👋 Привет! Я — *CurrencyBot 3.0*.\n"
                 "Могу конвертировать валюты, показывать графики и уведомлять о курсах.\n"
                 "Выбери действие:",
        "help": "📘 *Помощь*\n\n"
                "• /start — главное меню\n"
                "• /quick 100 USD to EUR — быстрая конвертация\n"
                "• /graph USD — график\n"
                "• /alert — уведомление\n"
                "• /theme dark — тема\n"
                "• /fav USD,EUR — избранное\n"
                "• /history — история",
        "convert": "💱 Введи сумму и валюту:\nНапример: `100 USD`",
        "history": "📜 Твоя история:",
        "no_history": "📜 История пуста.",
        "lang_set": "🌐 Язык установлен: ",
        "lang_error": "❌ Неподдерживаемый язык.",
        "alert_set": "✅ Уведомление установлено: ",
        "alert_error": "❌ Неверный формат. Пример: `/alert USD > 95`",
        "theme_set": "🎨 Тема установлена: ",
        "fav_set": "⭐ Избранное установлено: ",
        "fav_error": "❌ Неверный формат. Пример: `/fav USD,EUR`"
    },
    "en": {
        "start": "👋 Hi! I'm *CurrencyBot 3.0*.\n"
                 "I can convert currencies, show charts and notify you of rates.\n"
                 "Choose an action:",
        "help": "📘 *Help*\n\n"
                "• /start — main menu\n"
                "• /quick 100 USD to EUR — quick convert\n"
                "• /graph USD — chart\n"
                "• /alert — notify\n"
                "• /theme dark — theme\n"
                "• /fav USD,EUR — favorites\n"
                "• /history — history",
        "convert": "💱 Enter amount and currency:\nExample: `100 USD`",
        "history": "📜 Your history:",
        "no_history": "📜 History is empty.",
        "lang_set": "🌐 Language set to: ",
        "lang_error": "❌ Unsupported language.",
        "alert_set": "✅ Alert set: ",
        "alert_error": "❌ Invalid format. Example: `/alert USD > 95`",
        "theme_set": "🎨 Theme set to: ",
        "fav_set": "⭐ Favorites set to: ",
        "fav_error": "❌ Invalid format. Example: `/fav USD,EUR`"
    }
}

def t(user_data, key):
    lang = user_data.get('lang', 'ru')
    return LANGS[lang].get(key, LANGS['ru'][key])

# --- Темы ---
THEMES = {
    "light": {
        "menu": [
            ["💱 Convert", "📊 Rates"],
            ["📈 Chart", "🔔 Alerts"],
            ["🎨 Theme", "📜 History"],
            ["⭐ Favorites", "🧮 Calculator"]
        ]
    },
    "dark": {
        "menu": [
            ["💱 Convert", "📊 Rates"],
            ["📈 Chart", "🔔 Alerts"],
            ["🎨 Theme", "📜 History"],
            ["⭐ Favorites", "🧮 Calculator"]
        ]
    }
}

def get_menu(user_data):
    theme = user_data.get("theme", "light")
    lang = user_data.get("lang", "ru")
    menu = THEMES[theme]["menu"]
    if lang == "ru":
        menu = [
            ["💱 Конвертировать", "📊 Курсы"],
            ["📈 График", "🔔 Уведомления"],
            ["🎨 Тема", "📜 История"],
            ["⭐ Избранное", "🧮 Калькулятор"]
        ]
    return ReplyKeyboardMarkup(menu, resize_keyboard=True)

# --- /start ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    settings = get_user_settings(user_id)
    context.user_data.update(settings)

    if cache.is_expired():
        await cache.update_rates()

    # Получить последние 3 конвертации
    recent = get_recent_history(user_id, 3)
    buttons = []
    for from_curr, to_curr, amount, result in recent:
        text = f"{amount} {from_curr} → {to_curr}"
        callback = f"repeat:{from_curr}:{to_curr}:{amount}"
        buttons.append([InlineKeyboardButton(text, callback_data=callback)])

    text = t(context.user_data, "start")
    if buttons:
        text += "\n\n*Последние действия:*"
        reply_markup = InlineKeyboardMarkup(buttons)
        await update.message.reply_text(text, reply_markup=reply_markup, parse_mode='Markdown')
    else:
        await update.message.reply_text(text, parse_mode='Markdown')

    await update.message.reply_text("Выбери действие:", reply_markup=get_menu(context.user_data))

# --- /help ---
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(t(context.user_data, "help"), parse_mode='Markdown')

# --- /theme ---
async def theme_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not context.args:
        await update.message.reply_text("Use: /theme dark or /theme light")
        return
    theme = context.args[0]
    if theme in ["dark", "light"]:
        save_user_settings(user_id, theme=theme)
        context.user_data["theme"] = theme
        await update.message.reply_text(t(context.user_data, "theme_set") + theme)
        # Обновить меню
        await update.message.reply_text("Меню обновлено", reply_markup=get_menu(context.user_data))
    else:
        await update.message.reply_text("Темы: dark, light")

# --- /fav ---
async def fav_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not context.args:
        await update.message.reply_text(t(context.user_data, "fav_error"), parse_mode='Markdown')
        return
    favs = [f.upper() for f in context.args[0].split(",")]
    save_user_settings(user_id, favorites=favs)
    context.user_data["favorites"] = favs
    await update.message.reply_text(t(context.user_data, "fav_set") + ", ".join(favs))

# --- /convert ---
async def convert_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(t(context.user_data, "convert"), parse_mode='Markdown')
    context.user_data['awaiting'] = 'amount'

# --- /quick ---
async def quick_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = " ".join(context.args)
    match = re.match(r"([\d\+\-\*\/\(\)\.\s]+)\s*([A-Z]{3})\s+(?:to|в)\s+([A-Z]{3})", args, re.I)
    if not match:
        await update.message.reply_text("Используй: `/quick 100 USD to EUR`", parse_mode='Markdown')
        return
    expr, from_curr, to_curr = match.groups()
    try:
        amount = eval(expr)
    except:
        await update.message.reply_text("Ошибка в выражении")
        return
    from_curr = from_curr.upper()
    to_curr = to_curr.upper()
    if from_curr not in cache.rates or to_curr not in cache.rates:
        await update.message.reply_text("Неизвестная валюта")
        return
    result = cache.convert(amount, from_curr, to_curr)
    if result is None:
        await update.message.reply_text("Ошибка конвертации")
        return
    user_id = update.effective_user.id
    add_history(user_id, from_curr, to_curr, amount, result)
    await update.message.reply_text(f"✅ {amount} {from_curr} = {result:,.2f} {to_curr}")

# --- /graph ---
async def graph_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    if not args:
        await update.message.reply_text("Use: /graph USD")
        return
    currency = args[0].upper()
    if currency not in cache.rates:
        await update.message.reply_text("❌ Currency not found")
        return

    try:
        days = list(range(1, 8))
        base_rate = cache.rates[currency]
        rates = [base_rate * (1 + 0.005 * (i - 4)) for i in days]

        plt.figure(figsize=(10, 4))
        plt.plot(days, rates, marker='o', linewidth=2, color='#1976D2')
        plt.title(f"📉 {currency} Rate (Last 7 Days)", fontsize=14)
        plt.xlabel("Days")
        plt.ylabel("Rate (to USD)")
        plt.grid(True, alpha=0.3)

        img_buf = io.BytesIO()
        plt.savefig(img_buf, format='png', bbox_inches='tight')
        img_buf.seek(0)
        plt.close()

        await update.message.reply_photo(photo=img_buf, caption=f"📉 Chart for {currency}")
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {e}")

# --- /alert ---
async def alert_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Выбери валюту:", reply_markup=InlineKeyboardMarkup([
        [InlineKeyboardButton("USD", callback_data="alert_set:USD"),
         InlineKeyboardButton("EUR", callback_data="alert_set:EUR"),
         InlineKeyboardButton("RUB", callback_data="alert_set:RUB")]
    ]))

# --- /history ---
async def history_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    hist = get_recent_history(user_id, 10)
    if not hist:
        await update.message.reply_text(t(context.user_data, "no_history"))
        return
    lines = [f"• {amount} {from_curr} → {result:,.2f} {to_curr}" for from_curr, to_curr, amount, result in hist]
    text = t(context.user_data, "history") + "\n" + "\n".join(lines)
    await update.message.reply_text(text, parse_mode='Markdown')

# --- Обработка сообщений ---
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    user_id = update.effective_user.id
    settings = get_user_settings(user_id)
    context.user_data.update(settings)

    # Кнопки
    lang_map = {"💱 Конвертировать": "💱 Convert", "📊 Курсы": "📊 Rates", "📈 График": "📈 Chart",
                "🔔 Уведомления": "🔔 Alerts", "🎨 Тема": "🎨 Theme", "📜 История": "📜 History",
                "⭐ Избранное": "⭐ Favorites", "🧮 Калькулятор": "🧮 Calculator"}
    en_text = lang_map.get(text, text)

    if en_text in ["💱 Convert", "💱 Конвертировать"]:
        return await convert_command(update, context)
    elif en_text in ["📊 Rates", "📊 Курсы"]:
        return await show_rates(update, context)
    elif en_text in ["📈 Chart", "📈 График"]:
        return await update.message.reply_text("Use: /graph USD")
    elif en_text in ["🔔 Alerts", "🔔 Уведомления"]:
        return await alert_command(update, context)
    elif en_text in ["🎨 Theme", "🎨 Тема"]:
        return await update.message.reply_text("Use: /theme dark or /theme light")
    elif en_text in ["📜 History", "📜 История"]:
        return await history_command(update, context)
    elif en_text in ["⭐ Favorites", "⭐ Избранное"]:
        favs = get_favorites(user_id)
        buttons = [[curr] for curr in favs]
        await update.message.reply_text("Избранные валюты:", reply_markup=ReplyKeyboardMarkup(buttons, resize_keyboard=True))
        context.user_data['awaiting'] = 'favorite_curr'
    elif en_text in ["🧮 Calculator", "🧮 Калькулятор"]:
        await update.message.reply_text("Введите выражение: `100 + 50 USD to EUR`", parse_mode='Markdown')
        context.user_data['awaiting'] = 'calc'

    # Конвертация
    elif context.user_data.get('awaiting') == 'amount':
        match = re.match(r"(\d+(?:\.\d+)?)\s*([A-Z]{3})", text, re.I)
        if match:
            amount, curr = match.groups()
            amount = float(amount)
            from_curr = curr.upper()
            if from_curr not in cache.rates:
                await update.message.reply_text("❌ Unknown currency")
                return
            context.user_data['amount'] = amount
            context.user_data['from_curr'] = from_curr
            favs = get_favorites(user_id)
            buttons = [[curr] for curr in favs if curr != from_curr][:3]
            buttons.append(["Назад"])
            await update.message.reply_text(
                f"Сумма: {amount} {curr}\nВыбери валюту:",
                reply_markup=ReplyKeyboardMarkup(buttons, resize_keyboard=True)
            )
            context.user_data['awaiting'] = 'to_currency'
        else:
            await update.message.reply_text("❌ Неверный формат. Пример: `100 USD`", parse_mode='Markdown')

    elif context.user_data.get('awaiting') == 'to_currency':
        if text == "Назад":
            context.user_data.clear()
            return await start(update, context)

        to_curr = text.upper()
        amount = context.user_data['amount']
        from_curr = context.user_data['from_curr']

        if to_curr not in cache.rates:
            await update.message.reply_text("❌ Unknown currency")
            return

        result = cache.convert(amount, from_curr, to_curr)
        if result is None:
            await update.message.reply_text("❌ Conversion failed")
            return

        add_history(user_id, from_curr, to_curr, amount, result)

        keyboard = [
            [InlineKeyboardButton("🔄 Swap", callback_data=f"swap:{amount}:{from_curr}:{to_curr}")],
            [InlineKeyboardButton("🔁 Again", callback_data="convert_again")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await update.message.reply_text(
            f"✅ *{amount:,.2f} {from_curr} = {result:,.2f} {to_curr}*",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
        context.user_data.clear()

    elif context.user_data.get('awaiting') == 'calc':
        match = re.match(r"([\d\+\-\*\/\(\)\.\s]+)\s*([A-Z]{3})\s+(?:to|в)\s+([A-Z]{3})", text, re.I)
        if not match:
            await update.message.reply_text("Ошибка. Пример: `100 + 50 USD to EUR`", parse_mode='Markdown')
            return
        expr, from_curr, to_curr = match.groups()
        try:
            amount = eval(expr)
        except:
            await update.message.reply_text("Ошибка в выражении")
            return
        from_curr = from_curr.upper()
        to_curr = to_curr.upper()
        if from_curr not in cache.rates or to_curr not in cache.rates:
            await update.message.reply_text("Неизвестная валюта")
            return
        result = cache.convert(amount, from_curr, to_curr)
        if result is None:
            await update.message.reply_text("Ошибка конвертации")
            return
        add_history(user_id, from_curr, to_curr, amount, result)
        await update.message.reply_text(f"🧮 {expr} {from_curr} = {result:,.2f} {to_curr}")
        context.user_data.clear()

    elif context.user_data.get('awaiting') == 'favorite_curr':
        from_curr = text.upper()
        if from_curr not in cache.rates:
            await update.message.reply_text("Неизвестная валюта")
            return
        context.user_data['from_curr'] = from_curr
        favs = get_favorites(user_id)
        buttons = [[curr] for curr in favs if curr != from_curr][:3]
        buttons.append(["Назад"])
        await update.message.reply_text("Выбери валюту:", reply_markup=ReplyKeyboardMarkup(buttons, resize_keyboard=True))
        context.user_data['awaiting'] = 'to_currency_from_fav'

    elif context.user_data.get('awaiting') == 'to_currency_from_fav':
        if text == "Назад":
            context.user_data.clear()
            return await start(update, context)
        to_curr = text.upper()
        from_curr = context.user_data['from_curr']
        if to_curr not in cache.rates:
            await update.message.reply_text("Неизвестная валюта")
            return
        # Запросим сумму
        await update.message.reply_text("Введите сумму:")
        context.user_data['to_curr'] = to_curr
        context.user_data['awaiting'] = 'amount_from_fav'

    elif context.user_data.get('awaiting') == 'amount_from_fav':
        try:
            amount = float(text)
        except:
            await update.message.reply_text("Неверная сумма")
            return
        from_curr = context.user_data['from_curr']
        to_curr = context.user_data['to_curr']
        result = cache.convert(amount, from_curr, to_curr)
        if result is None:
            await update.message.reply_text("Ошибка конвертации")
            return
        add_history(user_id, from_curr, to_curr, amount, result)
        await update.message.reply_text(f"✅ {amount} {from_curr} = {result:,.2f} {to_curr}")
        context.user_data.clear()

# --- Курсы валют ---
async def show_rates(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if cache.is_expired():
        await cache.update_rates()
    top_currencies = ["EUR", "RUB", "GBP", "JPY", "CNY", "KZT", "UZS"]
    base = "USD"
    message = f"*Курс {base} сегодня:*\n\n"
    for curr in top_currencies:
        rate = cache.rates.get(curr)
        if rate:
            message += f"💵 1 {base} = {rate:,.4f} {curr}\n"
    await update.message.reply_text(message, parse_mode='Markdown')

# --- Обработка кнопок ---
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    data = query.data

    if data.startswith("repeat:"):
        _, from_curr, to_curr, amount = data.split(":")
        amount = float(amount)
        result = cache.convert(amount, from_curr, to_curr)
        if result is not None:
            await query.edit_message_text(f"🔁 {amount} {from_curr} = {result:,.2f} {to_curr}")
        else:
            await query.edit_message_text("Ошибка")

    elif data.startswith("alert_set:"):
        _, currency = data.split(":")
        context.user_data['alert_currency'] = currency
        await query.message.reply_text(f"Введите условие: `{currency} > 90`", parse_mode='Markdown')
        context.user_data['awaiting'] = 'alert_condition'

    elif data.startswith("swap:"):
        _, amount, from_curr, to_curr = data.split(":")
        result = cache.convert(float(amount), to_curr, from_curr)
        if result is not None:
            await query.edit_message_text(
                f"🔄 *{amount} {to_curr} = {result:,.2f} {from_curr}*",
                parse_mode='Markdown',
                reply_markup=query.message.reply_markup
            )

    elif data == "convert_again":
        await query.message.reply_text(t(context.user_data, "convert"), parse_mode='Markdown')
        context.user_data['awaiting'] = 'amount'

# --- Обработка условия уведомления ---
async def handle_alert_condition(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data.get('awaiting') != 'alert_condition':
        return
    text = update.message.text.strip()
    match = re.match(r"([A-Z]{3})\s*([<>])\s*([\d\.]+)", text)
    if not match:
        await update.message.reply_text("Неверный формат. Пример: `USD > 90`")
        return
    currency, op, target = match.groups()
    target = float(target)
    user_id = update.effective_user.id
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("INSERT INTO alerts (user_id, currency, operator, target) VALUES (?, ?, ?, ?)",
                (user_id, currency, op, target))
    conn.commit()
    conn.close()
    await update.message.reply_text(f"✅ Уведомление установлено: {currency} {op} {target}")
    context.user_data.pop('awaiting', None)

# --- Inline-режим ---
async def inline_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.inline_query.query.strip()
    if not query:
        return

    if cache.is_expired():
        await cache.update_rates()

    results = []

    match_convert = re.match(r"(\d+(?:\.\d+)?)\s*([A-Z]{3})\s+(?:to|в)\s+([A-Z]{3})", query, re.I)
    if match_convert:
        amount, from_curr, to_curr = match_convert.groups()
        amount = float(amount)
        result_amount = cache.convert(amount, from_curr.upper(), to_curr.upper())
        if result_amount is not None:
            results.append({
                "type": "article",
                "id": "convert",
                "title": f"{amount} {from_curr} → {to_curr}",
                "description": f"{result_amount:,.2f} {to_curr}",
                "input_message_content": {"message_text": f"{amount} {from_curr} = {result_amount:,.2f} {to_curr}"}
            })
    else:
        match_simple = re.match(r"(\d+(?:\.\d+)?)\s*([A-Z]{3})", query, re.I)
        if match_simple:
            amount, curr = match_simple.groups()
            amount = float(amount)
            curr = curr.upper()
            user_id = update.effective_user.id
            settings = get_user_settings(user_id)
            favs = settings["favorites"]
            targets = favs if favs else ["EUR", "RUB", "GBP"]
            for t in targets:
                if t != curr and t in cache.rates:
                    converted = cache.convert(amount, curr, t)
                    if converted is not None:
                        results.append({
                            "type": "article",
                            "id": f"{curr}_{t}_{amount}",
                            "title": f"{amount} {curr}",
                            "description": f"→ {converted:,.2f} {t}",
                            "input_message_content": {"message_text": f"{amount} {curr} = {converted:,.2f} {t}"}
                        })
        else:
            match_curr = re.match(r"([A-Z]{3})", query, re.I)
            if match_curr:
                curr = match_curr.group(1).upper()
                if curr in cache.rates:
                    rate = cache.rates[curr]
                    results.append({
                        "type": "article",
                        "id": curr,
                        "title": f"Rate {curr}",
                        "description": f"1 USD = {rate:.4f} {curr}",
                        "input_message_content": {"message_text": f"Rate {curr}: 1 USD = {rate:.4f} {curr}"}
                    })

    if not results:
        results.append({
            "type": "article",
            "id": "help",
            "title": "Examples",
            "description": "100 USD, 50 EUR to RUB",
            "input_message_content": {"message_text": "Examples:\n• 100 USD\n• 50 EUR to RUB\n• @bot 10 USD"}
        })

    await update.inline_query.answer(results, cache_time=1, is_personal=True)

# --- Фоновая задача: проверка уведомлений ---
async def check_alerts(context: ContextTypes.DEFAULT_TYPE):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT id, user_id, currency, operator, target FROM alerts")
    alerts = cur.fetchall()
    for alert_id, user_id, curr, op, target in alerts:
        rate = cache.rates.get(curr)
        if not rate:
            continue
        triggered = False
        if op == ">" and rate > target:
            triggered = True
        elif op == "<" and rate < target:
            triggered = True
        if triggered:
            try:
                await context.bot.send_message(user_id, f"🔔 Alert: {curr} = {rate} → condition met!")
                cur.execute("DELETE FROM alerts WHERE id=?", (alert_id,))
                conn.commit()
            except:
                pass
    conn.close()

# --- Запуск ---
def main():
    if not TOKEN:
        print("❌ TOKEN not set")
        return
    print("🚀 Starting CurrencyBot 3.0...")
    app = Application.builder().token(TOKEN).build()

    # Обработчики
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("theme", theme_command))
    app.add_handler(CommandHandler("fav", fav_command))
    app.add_handler(CommandHandler("convert", convert_command))
    app.add_handler(CommandHandler("quick", quick_command))
    app.add_handler(CommandHandler("graph", graph_command))
    app.add_handler(CommandHandler("alert", alert_command))
    app.add_handler(CommandHandler("history", history_command))
    app.add_handler(CommandHandler("rates", show_rates))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(InlineQueryHandler(inline_query))

    # Фоновая задача
    app.job_queue.run_repeating(check_alerts, interval=60, first=10)

    app.run_polling()

if __name__ == "__main__":
    main()
