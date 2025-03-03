import os
import random
import logging
from datetime import datetime
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
    MessageHandler,
    ConversationHandler
)

import database as db

# Загрузка переменных окружения
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
CHANNEL_USERNAME = os.getenv("CHANNEL_USERNAME")

# Настройка логирования
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# Константы для разговора
TEXT, END_DATE = range(2)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик команды /start."""
    await update.message.reply_text(
        f"Привет! Я бот для проведения розыгрышей в канале {CHANNEL_USERNAME}.\n"
        "Используйте /create_raffle для создания нового розыгрыша.\n"
        "Используйте /list_raffles для просмотра активных розыгрышей.\n"
        "Используйте /draw_winner для определения победителя в розыгрыше."
    )

async def create_raffle_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Начало создания розыгрыша."""
    await update.message.reply_text(
        "Давайте создадим розыгрыш. Отправьте текст поста для розыгрыша:"
    )
    return TEXT

async def raffle_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Получение текста розыгрыша."""
    context.user_data["raffle_text"] = update.message.text
    await update.message.reply_text(
        "Отлично! Теперь укажите дату окончания розыгрыша в формате ГГГГ-ММ-ДД ЧЧ:ММ\n"
        "Например: 2023-12-31 18:00"
    )
    return END_DATE

async def raffle_end_date(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Получение даты окончания розыгрыша и создание поста."""
    try:
        end_date = datetime.strptime(update.message.text, "%Y-%m-%d %H:%M").isoformat()
    except ValueError:
        await update.message.reply_text(
            "Неверный формат даты. Пожалуйста, используйте формат ГГГГ-ММ-ДД ЧЧ:ММ"
        )
        return END_DATE
    
    raffle_text = context.user_data["raffle_text"]
    
    # Создаем клавиатуру
    keyboard = [[InlineKeyboardButton("Участвую", callback_data="participate")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    # Отправляем сообщение в канал
    try:
        message = await context.bot.send_message(
            chat_id=CHANNEL_USERNAME,
            text=f"{raffle_text}\n\nРозыгрыш завершится: {update.message.text}",
            reply_markup=reply_markup
        )
        
        # Сохраняем розыгрыш в базе данных
        raffle_id = db.create_raffle(message.message_id, raffle_text, end_date)
        
        await update.message.reply_text(
            f"Розыгрыш успешно создан! ID розыгрыша: {raffle_id}"
        )
    except Exception as e:
        logger.error(f"Error creating raffle: {e}")
        await update.message.reply_text(
            f"Ошибка при создании розыгрыша: {str(e)}\n"
            f"Проверьте, добавлен ли бот в администраторы канала {CHANNEL_USERNAME}"
        )
    
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Отмена создания розыгрыша."""
    await update.message.reply_text("Создание розыгрыша отменено.")
    return ConversationHandler.END

async def participate_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработка нажатия на кнопку 'Участвую'."""
    query = update.callback_query
    await query.answer()
    
    # Информация о пользователе
    user = query.from_user
    user_id = user.id
    username = user.username or ""
    first_name = user.first_name or ""
    last_name = user.last_name or ""
    
    # ID сообщения используется как ID розыгрыша
    raffle_id = str(query.message.message_id)
    
    # Проверяем, что розыгрыш существует и активен
    raffle = db.get_raffle(raffle_id)
    if not raffle or not raffle.get("is_active", False):
        await query.message.reply_text(
            "Извините, этот розыгрыш уже завершен или не существует.",
            reply_to_message_id=query.message.message_id
        )
        return
    
    # Проверяем, подписан ли пользователь на канал
    try:
        chat_member = await context.bot.get_chat_member(CHANNEL_USERNAME, user_id)
        is_member = chat_member.status in ['member', 'administrator', 'creator']
        
        if not is_member:
            await context.bot.send_message(
                chat_id=user_id,
                text=f"Для участия в розыгрыше необходимо быть подписанным на канал {CHANNEL_USERNAME}."
            )
            return
        
        # Добавляем пользователя как участника
        is_new = db.add_participant(raffle_id, user_id, username, first_name, last_name)
        
        if is_new:
            await context.bot.send_message(
                chat_id=user_id,
                text=f"Вы успешно зарегистрированы для участия в розыгрыше!"
            )
        else:
            await context.bot.send_message(
                chat_id=user_id,
                text=f"Вы уже зарегистрированы для участия в этом розыгрыше."
            )
    
    except Exception as e:
        logger.error(f"Error processing participation: {e}")
        await context.bot.send_message(
            chat_id=user_id,
            text="Произошла ошибка при регистрации участия. Пожалуйста, попробуйте позже."
        )

async def list_raffles(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Показывает список активных розыгрышей."""
    active_raffles = db.get_active_raffles()
    
    if not active_raffles:
        await update.message.reply_text("В настоящее время нет активных розыгрышей.")
        return
    
    reply_text = "Активные розыгрыши:\n\n"
    for raffle in active_raffles:
        end_date = datetime.fromisoformat(raffle["end_date"]).strftime("%Y-%m-%d %H:%M")
        participants_count = len(db.get_participants(raffle["raffle_id"]))
        
        reply_text += f"ID: {raffle['raffle_id']}\n"
        reply_text += f"Текст: {raffle['text'][:50]}...\n"
        reply_text += f"Дата окончания: {end_date}\n"
        reply_text += f"Участников: {participants_count}\n\n"
    
    await update.message.reply_text(reply_text)

async def draw_winner_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Команда для определения победителя."""
    active_raffles = db.get_active_raffles()
    
    if not active_raffles:
        await update.message.reply_text("В настоящее время нет активных розыгрышей.")
        return
    
    # Создаем клавиатуру для выбора розыгрыша
    keyboard = []
    for raffle in active_raffles:
        participants_count = len(db.get_participants(raffle["raffle_id"]))
        button_text = f"ID: {raffle['raffle_id']} (Участников: {participants_count})"
        keyboard.append([InlineKeyboardButton(button_text, callback_data=f"draw_{raffle['raffle_id']}")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "Выберите розыгрыш для определения победителя:",
        reply_markup=reply_markup
    )

async def draw_winner_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Определение победителя в выбранном розыгрыше."""
    query = update.callback_query
    await query.answer()
    
    # Извлекаем ID розыгрыша из callback_data
    raffle_id = query.data.replace("draw_", "")
    
    # Получаем информацию о розыгрыше
    raffle = db.get_raffle(raffle_id)
    if not raffle or not raffle.get("is_active", False):
        await query.edit_message_text("Этот розыгрыш уже завершен или не существует.")
        return
    
    # Получаем список участников
    participants = db.get_participants(raffle_id)
    
    if not participants:
        await query.edit_message_text("В этом розыгрыше нет участников.")
        return
    
    # Выбираем случайного победителя
    winner = random.choice(participants)
    winner_id = winner["user_id"]
    winner_name = winner.get("first_name", "")
    if winner.get("last_name"):
        winner_name += f" {winner.get('last_name')}"
    winner_username = winner.get("username", "")
    
    # Обновляем информацию о розыгрыше
    db.set_winner(raffle_id, winner_id)
    
    # Формируем текст объявления победителя
    winner_text = f"🎉 Победитель розыгрыша определен! 🎉\n\n"
    winner_text += f"Розыгрыш: {raffle['text'][:100]}...\n\n"
    winner_text += f"Победитель: {winner_name}"
    if winner_username:
        winner_text += f" (@{winner_username})"
    
    # Отправляем сообщение в канал
    try:
        await context.bot.send_message(
            chat_id=CHANNEL_USERNAME,
            text=winner_text,
            reply_to_message_id=int(raffle_id)
        )
        
        await query.edit_message_text(f"Победитель успешно определен и объявлен в канале!")
    except Exception as e:
        logger.error(f"Error announcing winner: {e}")
        await query.edit_message_text(f"Ошибка при объявлении победителя: {str(e)}")

def main() -> None:
    """Запуск бота."""
    if not BOT_TOKEN or not CHANNEL_USERNAME:
        logger.error("Пожалуйста, укажите BOT_TOKEN и CHANNEL_USERNAME в файле .env")
        return
    
    # Создаем приложение
    application = Application.builder().token(BOT_TOKEN).build()

    # Добавляем обработчики команд
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("list_raffles", list_raffles))
    application.add_handler(CommandHandler("draw_winner", draw_winner_start))
    
    # Добавляем обработчик для создания розыгрыша
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("create_raffle", create_raffle_start)],
        states={
            TEXT: [MessageHandler(filters.TEXT & ~filters.COMMAND, raffle_text)],
            END_DATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, raffle_end_date)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )
    application.add_handler(conv_handler)
    
    # Добавляем обработчики callback запросов
    application.add_handler(CallbackQueryHandler(participate_callback, pattern="^participate$"))
    application.add_handler(CallbackQueryHandler(draw_winner_callback, pattern="^draw_"))
    
    # Запускаем бота
    application.run_polling()

if __name__ == "__main__":
    main() 