# main.py — CurrencyBot 2.0

import os
import re
import requests
import matplotlib.pyplot as plt
import io
from datetime import datetime, timedelta
from telegram import Update, InlineQueryResultArticle, InputTextMessageContent, \
    InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, \
    filters, CallbackQueryHandler, InlineQueryHandler, JobQueue

# ===================================
TOKEN = os.getenv("TOKEN")
# ===================================

job_queue = JobQueue()

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
alerts = []  # [{user_id, currency, operator, target}]

# --- Языки ---
LANGS = {
    "ru": {
        "start": "👋 Привет! Я — *CurrencyBot 2.0*.\n"
                 "Могу конвертировать валюты, показывать графики и уведомлять о курсах.\n"
                 "Выбери действие:",
        "help": "📘 *Помощь*\n\n"
                "• /start — главное меню\n"
                "• /convert — конвертация\n"
                "• /graph USD — график\n"
                "• /alert USD > 95 — уведомление\n"
                "• /lang en — сменить язык\n"
                "• /history — история",
        "convert": "💱 Введи сумму и валюту:\nНапример: `100 USD`",
        "history": "📜 Твоя история:",
        "no_history": "📜 История пуста.",
        "lang_set": "🌐 Язык установлен: ",
        "lang_error": "❌ Неподдерживаемый язык.",
        "alert_set": "✅ Уведомление установлено: ",
        "alert_error": "❌ Неверный формат. Пример: `/alert USD > 95`"
    },
    "en": {
        "start": "👋 Hi! I'm *CurrencyBot 2.0*.\n"
                 "I can convert currencies, show charts and notify you of rates.\n"
                 "Choose an action:",
        "help": "📘 *Help*\n\n"
                "• /start — main menu\n"
                "• /convert — convert\n"
                "• /graph USD — chart\n"
                "• /alert USD > 95 — notify\n"
                "• /lang ru — change language\n"
                "• /history — history",
        "convert": "💱 Enter amount and currency:\nExample: `100 USD`",
        "history": "📜 Your history:",
        "no_history": "📜 History is empty.",
        "lang_set": "🌐 Language set to: ",
        "lang_error": "❌ Unsupported language.",
        "alert_set": "✅ Alert set: ",
        "alert_error": "❌ Invalid format. Example: `/alert USD > 95`"
    }
}

def t(user_data, key):
    lang = user_data.get('lang', 'ru')
    return LANGS[lang].get(key, LANGS['ru'][key])

# --- Меню ---
def get_menu(user_data):
    lang = user_data.get('lang', 'ru')
    if lang == 'en':
        return ReplyKeyboardMarkup([
            ["💱 Convert", "📊 Rates"],
            ["📈 Chart", "🔔 Alerts"],
            ["🌍 Language", "📜 History"]
        ], resize_keyboard=True)
    else:
        return ReplyKeyboardMarkup([
            ["💱 Конвертировать", "📊 Курсы"],
            ["📈 График", "🔔 Уведомления"],
            ["🌍 Язык", "📜 История"]
        ], resize_keyboard=True)

# --- /start ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if cache.is_expired():
        await cache.update_rates()
    await update.message.reply_text(
        t(context.user_data, "start"),
        reply_markup=get_menu(context.user_data),
        parse_mode='Markdown'
    )

# --- /help ---
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(t(context.user_data, "help"), parse_mode='Markdown')

# --- /lang ---
async def lang_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Use: /lang ru or /lang en")
        return
    lang = context.args[0]
    if lang in LANGS:
        context.user_data['lang'] = lang
        await update.message.reply_text(t(context.user_data, "lang_set") + lang)
    else:
        await update.message.reply_text(t(context.user_data, "lang_error"))

# --- /convert ---
async def convert_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(t(context.user_data, "convert"), parse_mode='Markdown')
    context.user_data['awaiting'] = 'amount'

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
        # Симуляция данных (в реальности можно использовать историю)
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
    user_id = update.effective_user.id
    args = context.args
    if len(args) != 3:
        await update.message.reply_text(t(context.user_data, "alert_error"), parse_mode='Markdown')
        return
    curr, op, target = args
    if op not in [">", "<"]:
        await update.message.reply_text(t(context.user_data, "alert_error"), parse_mode='Markdown')
        return
    try:
        target = float(target)
    except:
        await update.message.reply_text(t(context.user_data, "alert_error"), parse_mode='Markdown')
        return

    alerts.append({
        "user_id": user_id,
        "currency": curr.upper(),
        "operator": op,
        "target": target
    })
    await update.message.reply_text(t(context.user_data, "alert_set") + f"{curr} {op} {target}")

# --- /history ---
async def history_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    hist = context.user_data.get('history', [])
    if not hist:
        await update.message.reply_text(t(context.user_data, "no_history"))
        return
    text = t(context.user_data, "history") + "\n" + "\n".join(hist[-5:])
    await update.message.reply_text(text, parse_mode='Markdown')

# --- Обработка сообщений ---
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    lang = context.user_data.get('lang', 'ru')

    # Кнопки
    if text in ["💱 Конвертировать", "💱 Convert"]:
        return await convert_command(update, context)
    elif text in ["📊 Курсы", "📊 Rates"]:
        return await show_rates(update, context)
    elif text in ["📈 График", "📈 Chart"]:
        return await update.message.reply_text("Use: /graph USD")
    elif text in ["🔔 Уведомления", "🔔 Alerts"]:
        return await update.message.reply_text("Use: /alert USD > 95")
    elif text in ["🌍 Язык", "🌍 Language"]:
        return await update.message.reply_text("Use: /lang en or /lang ru")
    elif text in ["📜 История", "📜 History"]:
        return await history_command(update, context)
    elif text in ["ℹ️ Помощь", "ℹ️ Help"]:
        return await help_command(update, context)

    # Конвертация
    if context.user_data.get('awaiting') == 'amount':
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
            targets = ["EUR", "RUB", "GBP", "KZT", "UZS", "CNY"]
            buttons = [[t] for t in targets if t != from_curr][:3]
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

        # Сохранить в историю
        if 'history' not in context.user_data:
            context.user_data['history'] = []
        context.user_data['history'].append(f"{amount} {from_curr} → {result:,.2f} {to_curr}")
        context.user_data['history'] = context.user_data['history'][-5:]

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

    data = query.data

    if data.startswith("swap:"):
        _, amount, from_curr, to_curr = data.split(":")
        result = cache.convert(float(amount), to_curr, from_curr)
        if result is None:
            await query.edit_message_text("❌ Conversion failed")
            return
        await query.edit_message_text(
            f"🔄 *{amount} {to_curr} = {result:,.2f} {from_curr}*",
            parse_mode='Markdown',
            reply_markup=query.message.reply_markup
        )
    elif data == "convert_again":
        await query.message.reply_text(t(context.user_data, "convert"), parse_mode='Markdown')
        context.user_data['awaiting'] = 'amount'

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
            results.append(
                InlineQueryResultArticle(
                    id="convert",
                    title=f"{amount} {from_curr} → {to_curr}",
                    description=f"{result_amount:,.2f} {to_curr}",
                    input_message_content=InputTextMessageContent(
                        f"{amount} {from_curr} = {result_amount:,.2f} {to_curr}"
                    ),
                )
            )
    else:
        match_simple = re.match(r"(\d+(?:\.\d+)?)\s*([A-Z]{3})", query, re.I)
        if match_simple:
            amount, curr = match_simple.groups()
            amount = float(amount)
            curr = curr.upper()
            targets = ["EUR", "RUB", "GBP", "KZT", "UZS", "CNY"]
            for t in targets:
                if t != curr and t in cache.rates:
                    converted = cache.convert(amount, curr, t)
                    if converted is not None:
                        results.append(
                            InlineQueryResultArticle(
                                id=f"{curr}_{t}_{amount}",
                                title=f"{amount} {curr}",
                                description=f"→ {converted:,.2f} {t}",
                                input_message_content=InputTextMessageContent(
                                    f"{amount} {curr} = {converted:,.2f} {t}"
                                ),
                            )
                        )
        else:
            match_curr = re.match(r"([A-Z]{3})", query, re.I)
            if match_curr:
                curr = match_curr.group(1).upper()
                if curr in cache.rates:
                    rate = cache.rates[curr]
                    results.append(
                        InlineQueryResultArticle(
                            id=curr,
                            title=f"Rate {curr}",
                            description=f"1 USD = {rate:.4f} {curr}",
                            input_message_content=InputTextMessageContent(
                                f"Rate {curr}: 1 USD = {rate:.4f} {curr}"
                            ),
                        )
                    )

    if not results:
        results.append(
            InlineQueryResultArticle(
                id="help",
                title="Examples",
                description="100 USD, 50 EUR to RUB",
                input_message_content=InputTextMessageContent(
                    "Examples:\n• 100 USD\n• 50 EUR to RUB\n• @bot 10 USD"
                ),
            )
        )

    await update.inline_query.answer(results, cache_time=300, is_personal=True)

# --- Фоновая задача: проверка уведомлений ---
async def check_alerts(context: ContextTypes.DEFAULT_TYPE):
    for alert in alerts[:]:
        curr = alert["currency"]
        rate = cache.rates.get(curr)
        if not rate:
            continue
        triggered = False
        if alert["operator"] == ">" and rate > alert["target"]:
            triggered = True
        elif alert["operator"] == "<" and rate < alert["target"]:
            triggered = True

        if triggered:
            try:
                await context.bot.send_message(
                    alert["user_id"],
                    f"🔔 Alert: {curr} = {rate} → condition met!"
                )
                alerts.remove(alert)
            except:
                pass

# --- Запуск ---
def main():
    if not TOKEN:
        print("❌ TOKEN not set")
        return
    print("🚀 Starting CurrencyBot 2.0...")
    app = (Application.builder()
       .token(TOKEN)
       .job_queue(job_queue)
       .build())

    # Обработчики
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("lang", lang_command))
    app.add_handler(CommandHandler("convert", convert_command))
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
    import asyncio
    asyncio.run(main())
