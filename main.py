import os
import random
import logging
from datetime import datetime, timedelta
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
    MessageHandler,
    ConversationHandler,
    Job
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
TEXT, ASK_PHOTO, PHOTO, WINNERS_COUNT = range(4)  # Добавляем состояния для обработки фото

# Время ожидания ответа в секундах (10 минут)
CONVERSATION_TIMEOUT = 600

# Стандартная продолжительность розыгрыша в днях (используется для внутренней логики)
DEFAULT_RAFFLE_DURATION_DAYS = 30

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик команды /start."""
    await update.message.reply_text(
        f"Привет! Я бот для проведения розыгрышей в канале {CHANNEL_USERNAME}.\n"
        "Используйте /create_raffle для создания нового розыгрыша.\n"
        "Используйте /list_raffles для просмотра активных розыгрышей.\n"
        "Используйте /raffle_info для просмотра подробной информации о розыгрыше.\n"
        "Используйте /draw_winner для определения победителя в розыгрыше.\n"
        "Если что-то пошло не так, используйте /reset для сброса диалога."
    )

async def reset_conversation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Сброс состояния разговора."""
    # Очищаем данные пользователя
    context.user_data.clear()
    
    # Информируем пользователя о сбросе
    await update.message.reply_text(
        "Состояние разговора успешно сброшено. Теперь вы можете начать создание розыгрыша заново "
        "с помощью команды /create_raffle."
    )
    
    # Возвращаем ConversationHandler.END, чтобы сбросить любой активный разговор для этого пользователя
    return ConversationHandler.END

async def create_raffle_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Начало создания розыгрыша."""
    # Очищаем предыдущие данные пользователя для обеспечения "чистого" старта
    context.user_data.clear()
    
    # Устанавливаем таймер на завершение разговора
    context.user_data["conversation_end_time"] = datetime.now() + timedelta(seconds=CONVERSATION_TIMEOUT)
    
    await update.message.reply_text(
        "Давайте создадим розыгрыш. Отправьте текст поста для розыгрыша.\n\n"
        "Укажите всю информацию в тексте сообщения, включая условия и сроки розыгрыша.\n\n"
        "Если вы хотите отменить создание розыгрыша на любом этапе, отправьте /cancel."
    )
    return TEXT

async def raffle_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Получение текста розыгрыша."""
    try:
        # Обновляем таймер
        context.user_data["conversation_end_time"] = datetime.now() + timedelta(seconds=CONVERSATION_TIMEOUT)
        
        # Проверка, что сообщение получено
        message = update.message
        if not message:
            logger.error("Message is None in raffle_text handler")
            await update.effective_chat.send_message(
                "Произошла ошибка. Пожалуйста, начните заново с команды /create_raffle или сбросьте состояние с помощью /reset."
            )
            return ConversationHandler.END
        
        # Сохраняем текст сообщения
        if message.text:
            context.user_data["raffle_text"] = message.text
        else:
            await message.reply_text(
                "Пожалуйста, отправьте текстовое сообщение для розыгрыша."
            )
            return TEXT
        
        # Спрашиваем, хочет ли пользователь добавить изображение
        keyboard = [
            [InlineKeyboardButton("Да", callback_data="add_photo_yes")],
            [InlineKeyboardButton("Нет", callback_data="add_photo_no")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await message.reply_text(
            "Хотите добавить изображение к розыгрышу?",
            reply_markup=reply_markup
        )
        return ASK_PHOTO
    except Exception as e:
        logger.error(f"Error in raffle_text: {e}")
        await update.effective_chat.send_message(
            "Произошла ошибка при обработке текста. Пожалуйста, используйте /reset и попробуйте снова."
        )
        return ConversationHandler.END

async def ask_photo_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработка ответа на вопрос о добавлении фото."""
    try:
        query = update.callback_query
        await query.answer()
        
        choice = query.data
        
        if choice == "add_photo_yes":
            await query.edit_message_text(
                "Отправьте изображение для розыгрыша."
            )
            return PHOTO
        else:
            # Устанавливаем стандартную дату окончания (для внутренней логики)
            end_date = (datetime.now() + timedelta(days=DEFAULT_RAFFLE_DURATION_DAYS)).isoformat()
            context.user_data["end_date"] = end_date
            context.user_data["raffle_photo"] = None
            
            # Запрашиваем количество победителей
            await query.edit_message_text(
                "Укажите количество победителей (от 1 до 10):"
            )
            return WINNERS_COUNT
    except Exception as e:
        logger.error(f"Error in ask_photo_callback: {e}")
        await update.effective_chat.send_message(
            "Произошла ошибка. Пожалуйста, используйте /reset и попробуйте снова."
        )
        return ConversationHandler.END

async def raffle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработка отправленного изображения."""
    try:
        # Обновляем таймер
        context.user_data["conversation_end_time"] = datetime.now() + timedelta(seconds=CONVERSATION_TIMEOUT)
        
        # Проверяем, что пользователь отправил фото
        if not update.message.photo:
            await update.message.reply_text(
                "Пожалуйста, отправьте изображение для розыгрыша или нажмите /cancel чтобы пропустить этот шаг."
            )
            return PHOTO
        
        # Берем самое большое доступное фото
        largest_photo = update.message.photo[-1]
        file_id = largest_photo.file_id
        context.user_data["raffle_photo"] = file_id
        logger.info(f"Saved photo file_id: {file_id}")
        
        # Устанавливаем стандартную дату окончания (для внутренней логики)
        end_date = (datetime.now() + timedelta(days=DEFAULT_RAFFLE_DURATION_DAYS)).isoformat()
        context.user_data["end_date"] = end_date
        
        # Запрашиваем количество победителей
        await update.message.reply_text(
            "Укажите количество победителей (от 1 до 10):"
        )
        return WINNERS_COUNT
    except Exception as e:
        logger.error(f"Error in raffle_photo: {e}")
        await update.effective_chat.send_message(
            "Произошла ошибка при обработке изображения. Пожалуйста, используйте /reset и попробуйте снова."
        )
        return ConversationHandler.END

async def raffle_winners_count(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Получение количества победителей и создание розыгрыша."""
    try:
        winners_count = int(update.message.text)
        if winners_count < 1 or winners_count > 10:
            await update.message.reply_text(
                "Пожалуйста, укажите число от 1 до 10."
            )
            return WINNERS_COUNT
    except ValueError:
        await update.message.reply_text(
            "Пожалуйста, введите число от 1 до 10."
        )
        return WINNERS_COUNT
    except Exception as e:
        logger.error(f"Error in raffle_winners_count: {e}")
        await update.effective_chat.send_message(
            "Произошла ошибка. Пожалуйста, используйте /reset и попробуйте снова."
        )
        return ConversationHandler.END
    
    try:
        raffle_text = context.user_data["raffle_text"]
        raffle_photo = context.user_data.get("raffle_photo")
        end_date = context.user_data["end_date"]
        
        # Создаем клавиатуру
        keyboard = [[InlineKeyboardButton("Участвую", callback_data="participate")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        # Используем только текст пользователя без добавления даты окончания
        post_text = raffle_text
        
        # Отправляем сообщение в канал
        try:
            # Если есть фото, отправляем сообщение с фото
            if raffle_photo:
                message = await context.bot.send_photo(
                    chat_id=CHANNEL_USERNAME,
                    photo=raffle_photo,
                    caption=post_text,
                    reply_markup=reply_markup
                )
            # Иначе отправляем только текст
            else:
                message = await context.bot.send_message(
                    chat_id=CHANNEL_USERNAME,
                    text=post_text,
                    reply_markup=reply_markup
                )
            
            # Сохраняем розыгрыш в базе данных
            raffle_id = db.create_raffle(message.message_id, raffle_text, end_date, winners_count)
            
            # Если было фото, сохраняем его ID
            if raffle_photo:
                # Здесь можно было бы добавить в базу данных сохранение ссылки на фото,
                # но это потребует изменения структуры БД
                logger.info(f"Raffle {raffle_id} created with photo")
            
            winners_text = "победитель" if winners_count == 1 else "победителей"
            await update.message.reply_text(
                f"Розыгрыш успешно создан! ID розыгрыша: {raffle_id}\n"
                f"Количество {winners_text}: {winners_count}"
            )
            
            # Очищаем данные разговора после успешного завершения
            context.user_data.clear()
            
        except Exception as e:
            logger.error(f"Error creating raffle: {e}")
            await update.message.reply_text(
                f"Ошибка при создании розыгрыша: {str(e)}\n"
                f"Проверьте, добавлен ли бот в администраторы канала {CHANNEL_USERNAME}"
            )
            return ConversationHandler.END
        
        return ConversationHandler.END
    except Exception as e:
        logger.error(f"Unexpected error in raffle_winners_count: {e}")
        await update.effective_chat.send_message(
            "Произошла непредвиденная ошибка. Пожалуйста, используйте /reset и попробуйте снова."
        )
        return ConversationHandler.END

async def conversation_timeout(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик тайм-аута разговора."""
    job = context.job
    chat_id = job.data
    
    # Очищаем пользовательские данные при таймауте
    if "user_id" in job.data and job.data["user_id"] in context.user_data:
        context.user_data[job.data["user_id"]].clear()
    
    await context.bot.send_message(
        chat_id=chat_id,
        text="Время создания розыгрыша истекло. Пожалуйста, начните заново с команды /create_raffle."
    )

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Отмена создания розыгрыша."""
    # Очищаем данные пользователя при отмене
    context.user_data.clear()
    
    await update.message.reply_text(
        "Создание розыгрыша отменено. Вы можете начать заново с помощью команды /create_raffle."
    )
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
        try:
            # Отправляем сообщение лично пользователю, а не в канал
            await context.bot.send_message(
                chat_id=user_id,
                text="Извините, этот розыгрыш уже завершен или не существует."
            )
        except Exception as e:
            logger.error(f"Не удалось отправить личное сообщение пользователю о завершенном розыгрыше: {e}")
            # Если не удалось отправить личное сообщение, то просто отвечаем в callback
            await query.answer("Этот розыгрыш уже завершен", show_alert=True)
        return
    
    # Проверяем, подписан ли пользователь на канал
    try:
        chat_member = await context.bot.get_chat_member(CHANNEL_USERNAME, user_id)
        is_member = chat_member.status in ['member', 'administrator', 'creator']
        
        if not is_member:
            try:
                # Пытаемся отправить личное сообщение
                await context.bot.send_message(
                    chat_id=user_id,
                    text=f"Для участия в розыгрыше необходимо быть подписанным на канал {CHANNEL_USERNAME}."
                )
            except Exception as e:
                logger.error(f"Не удалось отправить личное сообщение пользователю: {e}")
                # Если не получилось отправить личное сообщение, ничего не делаем
                # Пользователь просто не получит уведомление
            return
        
        # Добавляем пользователя как участника
        is_new = db.add_participant(raffle_id, user_id, username, first_name, last_name)
        
        # Подготовим данные о количестве участников для обновления сообщения
        participants_count = len(db.get_participants(raffle_id))
        
        if is_new:
            try:
                # Пытаемся отправить личное сообщение
                await context.bot.send_message(
                    chat_id=user_id,
                    text=f"Вы успешно зарегистрированы для участия в розыгрыше!"
                )
            except Exception as e:
                logger.error(f"Не удалось отправить личное сообщение пользователю: {e}")
                # Если не получилось отправить личное сообщение, ничего критичного не происходит
                # Пользователь увидит обновленное сообщение с счетчиком участников
            
            # Обновляем сообщение с розыгрышем, показывая количество участников
            try:
                # Получаем оригинальную клавиатуру
                original_keyboard = query.message.reply_markup.inline_keyboard
                
                # Создаем новую клавиатуру с актуальной информацией об участниках
                keyboard = [[InlineKeyboardButton(f"Участвую ({participants_count})", callback_data="participate")]]
                reply_markup = InlineKeyboardMarkup(keyboard)
                
                # Определяем, есть ли у сообщения фото
                if query.message.photo:
                    # Если это сообщение с фото
                    await context.bot.edit_message_caption(
                        chat_id=query.message.chat.id,
                        message_id=query.message.message_id,
                        caption=query.message.caption,
                        reply_markup=reply_markup
                    )
                else:
                    # Если это текстовое сообщение
                    await context.bot.edit_message_text(
                        chat_id=query.message.chat.id,
                        message_id=query.message.message_id,
                        text=query.message.text,
                        reply_markup=reply_markup
                    )
            except Exception as e:
                logger.error(f"Ошибка при обновлении сообщения розыгрыша: {e}")
                # Если не получилось обновить сообщение, просто логируем ошибку
        else:
            try:
                # Пытаемся отправить личное сообщение
                await context.bot.send_message(
                    chat_id=user_id,
                    text=f"Вы уже зарегистрированы для участия в этом розыгрыше."
                )
            except Exception as e:
                logger.error(f"Не удалось отправить личное сообщение пользователю: {e}")
                # Если не получилось отправить личное сообщение, ничего критичного не происходит
    
    except Exception as e:
        logger.error(f"Error processing participation: {e}")
        try:
            await context.bot.send_message(
                chat_id=user_id,
                text="Произошла ошибка при регистрации участия. Пожалуйста, попробуйте позже."
            )
        except:
            # Если отправка сообщения не удалась, просто логируем ошибку
            logger.error("Не удалось отправить сообщение об ошибке пользователю")

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
        winners_count = raffle.get("winners_count", 1)
        
        reply_text += f"ID: {raffle['raffle_id']}\n"
        reply_text += f"Текст: {raffle['text'][:50]}...\n"
        reply_text += f"Дата окончания: {end_date}\n"
        reply_text += f"Участников: {participants_count}\n"
        reply_text += f"Победителей: {winners_count}\n\n"
    
    reply_text += "Для получения подробной информации о розыгрыше используйте команду /raffle_info"
    
    await update.message.reply_text(reply_text)

async def raffle_info_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Команда для получения подробной информации о розыгрыше."""
    # Получаем список всех розыгрышей (активных и неактивных)
    active_raffles = db.get_active_raffles()
    
    if not active_raffles:
        await update.message.reply_text("В настоящее время нет активных розыгрышей.")
        return
    
    # Создаем клавиатуру для выбора розыгрыша
    keyboard = []
    for raffle in active_raffles:
        participants_count = len(db.get_participants(raffle["raffle_id"]))
        button_text = f"ID: {raffle['raffle_id']} (Участников: {participants_count})"
        keyboard.append([InlineKeyboardButton(button_text, callback_data=f"info_{raffle['raffle_id']}")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "Выберите розыгрыш для просмотра подробной информации:",
        reply_markup=reply_markup
    )

async def raffle_info_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Отображение подробной информации о розыгрыше."""
    query = update.callback_query
    await query.answer()
    
    # Извлекаем ID розыгрыша из callback_data
    raffle_id = query.data.replace("info_", "")
    
    # Получаем информацию о розыгрыше
    raffle = db.get_raffle(raffle_id)
    if not raffle:
        await query.edit_message_text("Этот розыгрыш не существует.")
        return
    
    # Получаем список участников
    participants = db.get_participants(raffle_id)
    participants_count = len(participants)
    
    # Форматируем информацию о розыгрыше
    end_date = datetime.fromisoformat(raffle["end_date"]).strftime("%Y-%m-%d %H:%M")
    created_at = datetime.fromisoformat(raffle["created_at"]).strftime("%Y-%m-%d %H:%M")
    
    status = "Активен" if raffle.get("is_active", False) else "Завершен"
    winners_count = raffle.get("winners_count", 1)
    
    info_text = f"📊 *Информация о розыгрыше* 📊\n\n"
    info_text += f"*ID розыгрыша:* {raffle_id}\n"
    info_text += f"*Текст:* {raffle['text'][:100]}...\n"
    info_text += f"*Создан:* {created_at}\n"
    info_text += f"*Дата окончания:* {end_date}\n"
    info_text += f"*Статус:* {status}\n"
    info_text += f"*Количество победителей:* {winners_count}\n"
    info_text += f"*Количество участников:* {participants_count}\n\n"
    
    # Добавляем информацию о победителях, если розыгрыш завершен
    if not raffle.get("is_active", False):
        winners = raffle.get("winners", [])
        if winners and any(winner is not None for winner in winners):
            info_text += "*Победители:*\n"
            for i, winner_id in enumerate(winners, 1):
                if winner_id is None:
                    continue
                
                # Находим информацию о победителе среди участников
                winner_info = next((p for p in participants if p["user_id"] == winner_id), None)
                if winner_info:
                    winner_name = winner_info.get("first_name", "")
                    if winner_info.get("last_name"):
                        winner_name += f" {winner_info.get('last_name')}"
                    winner_username = winner_info.get("username", "")
                    
                    info_text += f"{i}. {winner_name}"
                    if winner_username:
                        info_text += f" (@{winner_username})"
                    info_text += "\n"
                else:
                    info_text += f"{i}. Пользователь ID: {winner_id}\n"
    
    # Добавляем список участников, если их не слишком много
    if participants_count > 0:
        if participants_count <= 30:  # Ограничиваем вывод списка участников
            info_text += "\n*Список участников:*\n"
            for i, participant in enumerate(participants, 1):
                participant_name = participant.get("first_name", "")
                if participant.get("last_name"):
                    participant_name += f" {participant.get('last_name')}"
                participant_username = participant.get("username", "")
                
                info_text += f"{i}. {participant_name}"
                if participant_username:
                    info_text += f" (@{participant_username})"
                info_text += "\n"
        else:
            info_text += "\n*Первые 30 участников:*\n"
            for i, participant in enumerate(participants[:30], 1):
                participant_name = participant.get("first_name", "")
                if participant.get("last_name"):
                    participant_name += f" {participant.get('last_name')}"
                participant_username = participant.get("username", "")
                
                info_text += f"{i}. {participant_name}"
                if participant_username:
                    info_text += f" (@{participant_username})"
                info_text += "\n"
            
            info_text += f"\n...и еще {participants_count - 30} участников."
    
    # Отправляем информацию о розыгрыше
    try:
        await query.edit_message_text(
            text=info_text,
            parse_mode="Markdown"
        )
    except Exception as e:
        logger.error(f"Error sending raffle info: {e}")
        # В случае ошибки из-за длинного текста, отправляем информацию без списка участников
        info_text = info_text.split("*Список участников:*")[0]
        info_text += "\n*Список участников слишком длинный для отображения.*"
        await query.edit_message_text(
            text=info_text,
            parse_mode="Markdown"
        )

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
        winners_count = raffle.get("winners_count", 1)
        button_text = f"ID: {raffle['raffle_id']} (Уч.: {participants_count}, Поб.: {winners_count})"
        keyboard.append([InlineKeyboardButton(button_text, callback_data=f"draw_{raffle['raffle_id']}")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "Выберите розыгрыш для определения победителей:",
        reply_markup=reply_markup
    )

async def draw_winner_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Определение победителей в выбранном розыгрыше."""
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
    
    # Определяем количество победителей
    winners_count = raffle.get("winners_count", 1)
    
    # Проверяем, что у нас достаточно участников
    if len(participants) < winners_count:
        await query.edit_message_text(
            f"В розыгрыше недостаточно участников ({len(participants)}) "
            f"для выбора {winners_count} победителей."
        )
        return
    
    # Проверяем подписку каждого участника на канал
    valid_participants = []
    
    for participant in participants:
        user_id = participant["user_id"]
        try:
            # Проверяем, подписан ли участник на канал
            chat_member = await context.bot.get_chat_member(CHANNEL_USERNAME, user_id)
            is_member = chat_member.status in ['member', 'administrator', 'creator']
            
            if is_member:
                valid_participants.append(participant)
            else:
                logger.info(f"Участник {user_id} больше не подписан на канал и исключен из розыгрыша")
        except Exception as e:
            logger.error(f"Ошибка при проверке подписки участника {user_id}: {e}")
            # В случае ошибки проверки (например, пользователь заблокировал бота)
            # мы исключаем участника из розыгрыша
    
    # Проверяем, достаточно ли осталось валидных участников
    if len(valid_participants) < winners_count:
        await query.edit_message_text(
            f"В розыгрыше недостаточно действительных участников ({len(valid_participants)}) "
            f"для выбора {winners_count} победителей. Некоторые участники отписались от канала."
        )
        return
    
    # Выбираем случайных победителей без повторений из числа подписанных
    winners = random.sample(valid_participants, winners_count)
    
    # Собираем ID победителей
    winner_ids = [winner["user_id"] for winner in winners]
    
    # Обновляем информацию о розыгрыше
    db.set_winners(raffle_id, winner_ids)
    
    # Формируем текст объявления победителей
    if winners_count == 1:
        winner = winners[0]
        winner_name = winner.get("first_name", "")
        if winner.get("last_name"):
            winner_name += f" {winner.get('last_name')}"
        winner_username = winner.get("username", "")
        
        winner_text = f"🎉 Победитель определен! 🎉\n\n"
        winner_text += f"Поздравляем: {winner_name}"
        if winner_username:
            winner_text += f" (@{winner_username})"
    else:
        winner_text = f"🎉 Определены {winners_count} победителей! 🎉\n\n"
        winner_text += "Поздравляем:\n"
        
        for i, winner in enumerate(winners, 1):
            winner_name = winner.get("first_name", "")
            if winner.get("last_name"):
                winner_name += f" {winner.get('last_name')}"
            winner_username = winner.get("username", "")
            
            winner_text += f"{i}. {winner_name}"
            if winner_username:
                winner_text += f" (@{winner_username})"
            winner_text += "\n"
    
    # Отправляем сообщение в канал
    try:
        await context.bot.send_message(
            chat_id=CHANNEL_USERNAME,
            text=winner_text,
            reply_to_message_id=int(raffle_id)
        )
        
        await query.edit_message_text(f"Победители успешно определены и объявлены в канале!")
    except Exception as e:
        logger.error(f"Error announcing winners: {e}")
        await query.edit_message_text(f"Ошибка при объявлении победителей: {str(e)}")

def main() -> None:
    """Запуск бота."""
    if not BOT_TOKEN or not CHANNEL_USERNAME:
        logger.error("Пожалуйста, укажите BOT_TOKEN и CHANNEL_USERNAME в файле .env")
        return
    
    # Создаем приложение
    application = Application.builder().token(BOT_TOKEN).build()
    
    # Добавляем обработчик для создания розыгрыша
    # ВАЖНО: ConversationHandler должен быть добавлен ПЕРВЫМ, 
    # чтобы иметь приоритет над другими обработчиками команд
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("create_raffle", create_raffle_start)],
        states={
            TEXT: [
                # Обрабатываем только текстовые сообщения для первого шага
                MessageHandler(filters.TEXT & ~filters.COMMAND, raffle_text),
                # Добавляем обработку команды отмены на каждом шаге
                CommandHandler("cancel", cancel)
            ],
            ASK_PHOTO: [
                # Обработка callback для выбора добавления фото
                CallbackQueryHandler(ask_photo_callback, pattern="^add_photo_"),
                # Обработка команды отмены
                CommandHandler("cancel", cancel)
            ],
            PHOTO: [
                # Обработка отправленного фото
                MessageHandler(filters.PHOTO, raffle_photo),
                # Обработка команды отмены
                CommandHandler("cancel", cancel)
            ],
            WINNERS_COUNT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, raffle_winners_count),
                # Обработка команды отмены
                CommandHandler("cancel", cancel)
            ],
        },
        fallbacks=[
            CommandHandler("cancel", cancel),
            # Добавляем сброс как запасной вариант
            CommandHandler("reset", reset_conversation)
        ],
        # Добавляем настройку тайм-аута: если пользователь не отвечает в течение 10 минут, разговор прекращается
        conversation_timeout=CONVERSATION_TIMEOUT,
        # Разрешаем запускать разговор заново при новой команде /create_raffle
        allow_reentry=True,
        # Название для журналирования
        name="raffle_creation"
    )
    application.add_handler(conv_handler)

    # Добавляем глобальный обработчик команды сброса
    application.add_handler(CommandHandler("reset", reset_conversation))
    
    # Добавляем остальные обработчики команд
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("list_raffles", list_raffles))
    application.add_handler(CommandHandler("raffle_info", raffle_info_start))
    application.add_handler(CommandHandler("draw_winner", draw_winner_start))
    
    # Добавляем обработчики callback запросов
    application.add_handler(CallbackQueryHandler(participate_callback, pattern="^participate$"))
    application.add_handler(CallbackQueryHandler(draw_winner_callback, pattern="^draw_"))
    application.add_handler(CallbackQueryHandler(raffle_info_callback, pattern="^info_"))
    
    # Запускаем бота
    application.run_polling()

if __name__ == "__main__":
    main() 