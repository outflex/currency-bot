# bot.py — CurrencyBot с интерфейсом и inline-режимом

import requests
import re
from telegram import Update, InlineQueryResultArticle, InputTextMessageContent, \
    InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, \
    filters, CallbackQueryHandler, InlineQueryHandler
from datetime import datetime, timedelta

# ===================================
# ⚠️ ЗАМЕНИ НА СВОЙ ТОКЕН
TOKEN = "8358744776:AAFjPOhuoNiu8PO6JB6pIJ7xWujlpK_KolU"
# ===================================

# --- Кэш курсов ---
class CurrencyCache:
    def __init__(self):
        self.rates = {}
        self.last_update = None
        self.base = "USD"

    async def update_rates(self):
        try:
            response = requests.get(f"https://api.exchangerate-api.com/v4/latest/{self.base}")
            data = response.json()
            self.rates = data["rates"]
            self.last_update = datetime.now()
            print("✅ Курсы обновлены")
        except Exception as e:
            print("❌ Ошибка загрузки курсов:", e)

    def is_expired(self):
        return self.last_update is None or datetime.now() - self.last_update > timedelta(hours=1)

    def convert(self, amount: float, from_curr: str, to_curr: str) -> float:
        if from_curr == to_curr:
            return amount
        usd_amount = amount / self.rates.get(from_curr, 1)
        return usd_amount * self.rates.get(to_curr, 1)

cache = CurrencyCache()

# --- Главное меню ---
def get_main_menu():
    keyboard = [
        [KeyboardButton("💱 Конвертировать валюту")],
        [KeyboardButton("📊 Курсы валют")],
        [KeyboardButton("ℹ️ Помощь")]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

# --- /start ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if cache.is_expired():
        await cache.update_rates()
    await update.message.reply_text(
        "👋 Привет! Я — *CurrencyBot*.\n"
        "Могу мгновенно конвертировать валюты и показать курсы.\n"
        "Выбери действие:",
        reply_markup=get_main_menu(),
        parse_mode='Markdown'
    )

# --- /rates ---
async def show_rates(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if cache.is_expired():
        await cache.update_rates()
    top_currencies = ["EUR", "RUB", "GBP", "JPY", "CNY", "KZT", "UZS"]
    base = "USD"
    message = f"*Курс {base} на сегодня:*\n\n"
    for curr in top_currencies:
        rate = cache.rates.get(curr)
        if rate:
            message += f"💵 1 {base} = {rate:,.4f} {curr}\n"
    await update.message.reply_text(message, parse_mode='Markdown')

# --- Начать конвертацию ---
async def ask_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Введите сумму и валюту:\nНапример: `100 USD`",
        parse_mode='Markdown'
    )
    context.user_data['awaiting'] = 'amount'

# --- Обработка сообщений ---
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()

    if text == "📊 Курсы валют":
        return await show_rates(update, context)
    elif text == "ℹ️ Помощь":
        return await help_command(update, context)
    elif text == "💱 Конвертировать валюту":
        return await ask_amount(update, context)

    if context.user_data.get('awaiting') == 'amount':
        match = re.match(r"(\d+(?:\.\d+)?)\s*([A-Z]{3})", text, re.I)
        if match:
            amount, curr = match.groups()
            context.user_data['amount'] = float(amount)
            context.user_data['from_curr'] = curr.upper()
            await update.message.reply_text(
                f"Сумма: {amount} {curr}\nТеперь укажи, в какую валюту конвертировать:",
                reply_markup=ReplyKeyboardMarkup([
                    ["EUR", "RUB", "USD"],
                    ["GBP", "CNY", "KZT"],
                    ["Назад"]
                ], resize_keyboard=True)
            )
            context.user_data['awaiting'] = 'to_currency'
        else:
            await update.message.reply_text("❌ Неверный формат. Пример: `100 USD`")

    elif context.user_data.get('awaiting') == 'to_currency':
        if text == "Назад":
            context.user_data.clear()
            return await start(update, context)

        to_curr = text.upper()
        amount = context.user_data['amount']
        from_curr = context.user_data['from_curr']

        if to_curr not in cache.rates:
            await update.message.reply_text("❌ Неизвестная валюта. Попробуй ещё.")
            return

        result = cache.convert(amount, from_curr, to_curr)

        keyboard = [
            [InlineKeyboardButton("🔄 Поменять местами", callback_data=f"swap:{amount}:{from_curr}:{to_curr}")],
            [InlineKeyboardButton("🔁 Конвертировать снова", callback_data="convert_again")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await update.message.reply_text(
            f"✅ *{amount:,.2f} {from_curr} = {result:,.2f} {to_curr}*",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
        context.user_data.clear()

# --- Обработка кнопок ---
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    data = query.data

    if data.startswith("swap:"):
        _, amount, from_curr, to_curr = data.split(":")
        result = cache.convert(float(amount), to_curr, from_curr)
        await query.edit_message_text(
            f"🔄 *{amount} {to_curr} = {result:,.2f} {from_curr}*",
            parse_mode='Markdown',
            reply_markup=query.message.reply_markup
        )
    elif data == "convert_again":
        await query.message.reply_text(
            "Введите сумму и валюту: `100 USD`",
            parse_mode='Markdown'
        )
        context.user_data['awaiting'] = 'amount'

# --- /help ---
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = (
        "📘 *CurrencyBot — помощь*\n\n"
        "Доступные режимы:\n"
        "• /start — интерфейс с кнопками\n"
        "• Пишите боту: `100 USD` → конвертируем\n"
        "• В любом чате: `@твой_бот 50 EUR` → inline-результат\n\n"
        "Поддерживаемые валюты: USD, EUR, RUB, GBP, JPY, CNY, KZT, UZS и др."
    )
    await update.message.reply_text(help_text, parse_mode='Markdown')

# --- INLINE-РЕЖИМ ---
async def inline_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.inline_query.query.strip()
    if not query:
        return

    if cache.is_expired():
        await cache.update_rates()

    results = []

    # Формат: 100 USD to RUB
    match_convert = re.match(r"(\d+(?:\.\d+)?)\s*([A-Z]{3})\s+(?:to|в)\s+([A-Z]{3})", query, re.I)
    if match_convert:
        amount, from_curr, to_curr = match_convert.groups()
        amount = float(amount)
        result_amount = cache.convert(amount, from_curr.upper(), to_curr.upper())
        if result_amount:
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
        # Формат: 100 USD
        match_simple = re.match(r"(\d+(?:\.\d+)?)\s*([A-Z]{3})", query, re.I)
        if match_simple:
            amount, curr = match_simple.groups()
            amount = float(amount)
            curr = curr.upper()
            targets = ["EUR", "RUB", "GBP", "KZT", "UZS", "CNY"]
            for t in targets:
                if t != curr and t in cache.rates:
                    converted = cache.convert(amount, curr, t)
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
            # Только валюта: USD
            match_curr = re.match(r"([A-Z]{3})", query, re.I)
            if match_curr:
                curr = match_curr.group(1).upper()
                if curr in cache.rates:
                    rate = cache.rates[curr]
                    results.append(
                        InlineQueryResultArticle(
                            id=curr,
                            title=f"Курс {curr}",
                            description=f"1 {curr} = {rate:.4f} USD",
                            input_message_content=InputTextMessageContent(
                                f"Курс {curr}: 1 {curr} = {rate:.4f} USD"
                            ),
                        )
                    )

    if not results:
        results.append(
            InlineQueryResultArticle(
                id="help",
                title="Примеры",
                description="100 USD, 50 EUR to RUB",
                input_message_content=InputTextMessageContent(
                    "Примеры:\n• 100 USD\n• 50 EUR to RUB\n• @твой_бот 10 USD"
                ),
            )
        )

    await update.inline_query.answer(results, cache_time=300, is_personal=True)

# --- Запуск бота ---
def main():
    print("🚀 Запускаем CurrencyBot (с inline-режимом)...")
    app = Application.builder().token(TOKEN).build()

    # Обычные команды и сообщения
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("rates", show_rates))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(CallbackQueryHandler(button_handler))

    # Inline-режим
    app.add_handler(InlineQueryHandler(inline_query))

    app.run_polling()

if __name__ == "__main__":
    main()
