from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    MessageHandler,
    ConversationHandler,
    ContextTypes,
    CommandHandler,
    filters,
)
import sqlite3
import requests

user_data = {}

ADD_INCOME, ADD_EXPENSE, DELETE_RECORD, CONVERT_CURRENCY, RESTART_BOT = range(5)

keyboard = ReplyKeyboardMarkup(
    [['+ Доход', '- Расход'], ['💰 Баланс', '📜 История'], ['🗑 Удалить запись', '📊 Статистика'], ['💸 Конвертация валют'],
     ['🔄 Перезапуск']],
    resize_keyboard=True
)

API_KEY = 'd721becb2d4bed01eb79f1fc'
API_URL = f'https://api.exchangerate-api.com/v4/latest/RUB'


def get_db_connection():
    conn = sqlite3.connect('financial_bot.db')
    conn.row_factory = sqlite3.Row
    return conn


def create_tables():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY,
        balance REAL DEFAULT 0
    )
    ''')
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        amount REAL,
        type TEXT,
        description TEXT,
        FOREIGN KEY(user_id) REFERENCES users(id)
    )
    ''')
    conn.commit()
    conn.close()


create_tables()


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT balance FROM users WHERE id = ?', (chat_id,))
    row = cursor.fetchone()
    if row is None:
        cursor.execute('INSERT INTO users (id) VALUES (?)', (chat_id,))
        conn.commit()
    await update.message.reply_text("Привет! Я бот для учёта твоих финансов.", reply_markup=keyboard)


async def income_request(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Введите сумму дохода:")
    return ADD_INCOME


async def expense_request(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Введите сумму расхода:")
    return ADD_EXPENSE


async def handle_income(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    try:
        amount = float(update.message.text)
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('UPDATE users SET balance = balance + ? WHERE id = ?', (amount, chat_id))
        cursor.execute('INSERT INTO history (user_id, amount, type, description) VALUES (?, ?, ?, ?)',
                       (chat_id, amount, 'income', f'{amount} руб (доход)'))
        conn.commit()
        await update.message.reply_text(f"Доход в {amount} руб добавлен.")
    except ValueError:
        await update.message.reply_text("Введите корректное число.")
    return ConversationHandler.END


async def handle_expense(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    try:
        amount = float(update.message.text)
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('UPDATE users SET balance = balance - ? WHERE id = ?', (amount, chat_id))
        cursor.execute('INSERT INTO history (user_id, amount, type, description) VALUES (?, ?, ?, ?)',
                       (chat_id, amount, 'expense', f'{amount} руб (расход)'))
        conn.commit()
        await update.message.reply_text(f"Расход в {amount} руб добавлен.")
    except ValueError:
        await update.message.reply_text("Введите корректное число.")
    return ConversationHandler.END


async def balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT balance FROM users WHERE id = ?', (chat_id,))
    row = cursor.fetchone()
    balance = row['balance'] if row else 0
    await update.message.reply_text(f"Текущий баланс: {balance} руб")


async def history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT amount, type, description FROM history WHERE user_id = ? ORDER BY id DESC LIMIT 10',
                   (chat_id,))
    rows = cursor.fetchall()
    if not rows:
        await update.message.reply_text("История пуста.")
    else:
        history_list = [f"{row['amount']} руб ({row['type']}) - {row['description']}" for row in rows]
        await update.message.reply_text("\n".join(history_list))


async def delete_record(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT id, amount, type, description FROM history WHERE user_id = ? ORDER BY id DESC', (chat_id,))
    rows = cursor.fetchall()
    if not rows:
        await update.message.reply_text("История пуста.")
        return ConversationHandler.END
    history_list = [f"{idx + 1}. {row['amount']} руб ({row['type']}) - {row['description']}" for idx, row in
                    enumerate(rows)]
    await update.message.reply_text("Выберите запись для удаления:\n" + "\n".join(history_list))
    return DELETE_RECORD


async def handle_delete(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    try:
        record_num = int(update.message.text) - 1
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT id FROM history WHERE user_id = ? ORDER BY id DESC', (chat_id,))
        rows = cursor.fetchall()
        if 0 <= record_num < len(rows):
            record_id = rows[record_num]['id']
            cursor.execute('DELETE FROM history WHERE id = ?', (record_id,))
            conn.commit()
            await update.message.reply_text(f"Запись с ID {record_id} удалена.")
        else:
            await update.message.reply_text("Неверный номер записи.")
    except ValueError:
        await update.message.reply_text("Введите корректный номер записи.")
    return ConversationHandler.END


async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT SUM(amount) FROM history WHERE user_id = ? AND type = "income"', (chat_id,))
    income = cursor.fetchone()[0] or 0
    cursor.execute('SELECT SUM(amount) FROM history WHERE user_id = ? AND type = "expense"', (chat_id,))
    expense = cursor.fetchone()[0] or 0
    await update.message.reply_text(f"📊 Статистика:\nДоход: {income} руб\nРасход: {expense} руб")


async def convert_currency(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Введите запрос в формате: <сумма> <из валюты> в <в валюту>\nПример: 100 USD в EUR")
    return CONVERT_CURRENCY


async def handle_conversion(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip().upper().replace(',', '.')
    parts = text.split()

    if len(parts) != 4 or parts[2] != 'В':
        await update.message.reply_text("Формат неверный. Пример: 100 USD в EUR")
        return ConversationHandler.END

    try:
        amount = float(parts[0])
        from_currency = parts[1]
        to_currency = parts[3]

        response = requests.get(API_URL)
        data = response.json()
        rates = data['rates']

        if from_currency not in rates or to_currency not in rates:
            await update.message.reply_text("Одна из валют не поддерживается.")
            return ConversationHandler.END

        # Переводим из from_currency в to_currency через базовую валюту (USD)
        usd_amount = amount / rates[from_currency]
        converted_amount = usd_amount * rates[to_currency]

        await update.message.reply_text(f"{amount} {from_currency} = {converted_amount:.2f} {to_currency}")
    except Exception as e:
        await update.message.reply_text(f"Ошибка при конвертации: {e}")

    return ConversationHandler.END


async def restart_bot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    conn = get_db_connection()
    cursor = conn.cursor()
    # Сброс баланса и истории
    cursor.execute('UPDATE users SET balance = 0 WHERE id = ?', (chat_id,))
    cursor.execute('DELETE FROM history WHERE user_id = ?', (chat_id,))
    conn.commit()
    await update.message.reply_text("Бот перезапущен. Баланс и история сброшены.", reply_markup=keyboard)
    return ConversationHandler.END


async def handle_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    if text == '+ Доход':
        return await income_request(update, context)
    elif text == '- Расход':
        return await expense_request(update, context)
    elif text == '💰 Баланс':
        return await balance(update, context)
    elif text == '📜 История':
        return await history(update, context)
    elif text == '🗑 Удалить запись':
        return await delete_record(update, context)
    elif text == '📊 Статистика':
        return await stats(update, context)
    elif text == '💸 Конвертация валют':
        return await convert_currency(update, context)
    elif text == '🔄 Перезапуск':
        return await restart_bot(update, context)
    else:
        await update.message.reply_text("Я не понимаю эту команду.")
    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Операция отменена.")
    return ConversationHandler.END


def main():
    app = ApplicationBuilder().token("7749947551:AAGDGe7tuYIc-31pospBYDTeO7NRCwyc9UY").build()

    conv_handler = ConversationHandler(
        entry_points=[MessageHandler(filters.TEXT, handle_menu)],
        states={
            ADD_INCOME: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_income)],
            ADD_EXPENSE: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_expense)],
            DELETE_RECORD: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_delete)],
            CONVERT_CURRENCY: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_conversion)],
            RESTART_BOT: [MessageHandler(filters.TEXT & ~filters.COMMAND, restart_bot)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(conv_handler)

    app.run_polling()


if __name__ == "__main__":
    main()
