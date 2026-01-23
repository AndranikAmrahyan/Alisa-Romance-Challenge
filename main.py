import logging
import asyncio
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, 
    CommandHandler, 
    MessageHandler, 
    filters, 
    ContextTypes,
    CallbackQueryHandler
)
from telegram.constants import ParseMode

import config
from database import Database
from ai_handler import AIHandler
import infrastructure

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Инициализация
db = Database()
ai = AIHandler()

# Глобальные переменные для отслеживания игр
active_games = {}  # {chat_id: {'check_task': task, 'last_check': datetime}}

# Блокировки для чатов, чтобы сообщения обрабатывались по очереди
chat_locks = {}

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /help - справка в стиле Алисы"""
    help_text = (
        f"<b>💁‍♀️ ГАЙД ДЛЯ ОСОБО ОДАРЕННЫХ</b>\n\n"
        f"Че, потерялся? 😏 Ладно, объясняю один раз.\n"
        f"Ты попал в игру <b>\"Влюби в себя Алису\"</b>. "
        f"Суть простая: я — неприступная и дерзкая, а вы пытаетесь растопить мое ледяное сердце.\n\n"
        
        f"<b>🎮 КАК НАЧАТЬ ИГРУ:</b>\n"
        f"Просто напиши одну из команд (только если игра не идет):\n"
        f"👉 <code>/start</code> или <code>/alisa</code>\n"
        f"👉 Или просто напиши: <i>\"Алиса приходи\"</i>, <i>\"Алиса го играть\"</i>\n\n"
        
        f"<b>💬 КАК СО МНОЙ ОБЩАТЬСЯ:</b>\n"
        f"Когда игра запущена, я реагирую на:\n"
        f"1. <b>Reply</b> (ответь на мое сообщение)\n"
        f"2. <b>Упоминание</b> (напиши <i>\"Алиса, ты красотка\"</i>)\n"
        f"3. <b>Команду</b> <code>{config.COMMAND_PREFIX}</code> (пример: <code>{config.COMMAND_PREFIX} привет</code>)\n\n"
        
        f"<b>📜 СПИСОК КОМАНД:</b>\n"
        f"• <code>/start</code> — Запустить игру (выбор сложности)\n"
        f"• <code>/help</code> — Вызвать эту справку (если забыл, как жить)\n"
        f"• <code>{config.COMMAND_PREFIX} текст</code> — Сказать мне что-то напрямую\n\n"
        
        f"<i>P.S. Если я молчу — значит, вы скучные или я занята. Или просто игнорю, потому что могу. 💅</i>"
    )
    
    await update.message.reply_text(help_text, parse_mode=ParseMode.HTML)

async def on_new_chat_members(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Приветствие при добавлении в новый чат"""
    for member in update.message.new_chat_members:
        # Если добавили самого бота
        if member.id == context.bot.id:
            await help_command(update, context)
            return

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда запуска - предлагает выбор сложности"""
    chat_id = update.effective_chat.id
    chat_type = update.effective_chat.type
    
    # Проверяем, что бот в группе
    if chat_type == "private":
        keyboard = [[InlineKeyboardButton("➕ Добавить в группу", url=f"https://t.me/{context.bot.username}?startgroup=true")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            f"Эй, {update.effective_user.first_name}! 👋\n\n"
            f"Я {config.BOT_NAME}, и я работаю только в ГРУППАХ, а не в личке.\n"
            f"Добавь меня в свою группу и там запусти /start, /alisa или \"Алиса приходи\" 😏",
            reply_markup=reply_markup
        )
        return

    if db.is_game_active(chat_id):
        await update.message.reply_text(
            f"Игра уже идет! Не тупи 🙄\n"
            f"Пиши мне сообщения, используй {config.COMMAND_PREFIX} или просто отвечай на мои сообщения."
        )
        return
    
    # Предлагаем выбрать сложность
    keyboard = [
        [
            InlineKeyboardButton("😇 Легкая (Easy)", callback_data=f"diff|easy|{update.effective_user.id}"),
            InlineKeyboardButton("😐 Средняя (Medium)", callback_data=f"diff|medium|{update.effective_user.id}")
        ],
        [
            InlineKeyboardButton("👿 Сложная (Hard)", callback_data=f"diff|hard|{update.effective_user.id}")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        f"Так, стоп. Как будем играть? 😏\nВыбирай сложность, {update.effective_user.first_name}:",
        reply_markup=reply_markup
    )

async def difficulty_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка нажатия на кнопку сложности"""
    query = update.callback_query
    await query.answer()
    
    data = query.data.split("|")
    if len(data) != 3 or data[0] != "diff":
        return
        
    difficulty = data[1]
    initiator_id = int(data[2])
    
    # Проверка, что нажал тот, кто запустил
    if query.from_user.id != initiator_id:
        await query.answer("Эй! Не ты запускал, не тебе выбирать 😡", show_alert=True)
        return

    # Удаляем кнопки
    await query.edit_message_reply_markup(reply_markup=None)
    
    # Запускаем игру с выбранной сложностью
    await start_new_game_logic(update, context, difficulty)

async def start_new_game_logic(update: Update, context: ContextTypes.DEFAULT_TYPE, difficulty: str = "hard"):
    """Логика запуска новой игры (БД + приветствие)"""
    chat_id = update.effective_chat.id
    
    # Сброс и старт в БД
    db.start_game(chat_id, difficulty)
    
    if difficulty == "easy":
        # Текст для ЛЕГКОЙ сложности
        intro_message = f"""Ну здарова, пацаны 👋

Я {config.BOT_NAME}, я {config.BOT_AGE}, из {config.BOT_CITY}. Слышала, вы тут типа хотите в меня влюбиться? 😊 Ха, посмотрим, кто из вас на это способен...

🎮 КАК ИГРАТЬ:
Пишите мне сообщения и пытайтесь меня впечатлить. Я довольно открытая к новым знакомствам 😉

Обращаться ко мне можно:
• Ответом на МОЕ сообщение (reply)
• Командой {config.COMMAND_PREFIX} твой_текст
• Упоминанием моего имени ({config.BOT_NAME}) в сообщении

⚠️ ПРАВИЛА (Easy Mode):
- Будьте милыми и искренними
- Я ценю честность и чувство юмора
- Не нужно быть слишком дерзким - я люблю уважение

🏆 ПОБЕДА:
Когда я пойму, что влюбилась в кого-то из вас — скажу это сама и назову имя победителя. Игра закончится.

Если вы будете молчать больше {int(config.CHECK_INTERVAL/60)} минут — я уйду (закончу игру).
Сами виноваты, придется начинать заново 🤷‍♀️

Ну что, кто первый решится? Или все стесняетесь? 😊"""

    elif difficulty == "medium":
        # Текст для СРЕДНЕЙ сложности
        intro_message = f"""Ну здарова, пацаны 👋

Я {config.BOT_NAME}, я {config.BOT_AGE}, из {config.BOT_CITY}. Слышала, вы тут типа хотите в меня влюбиться? 😏 Ха, посмотрим, кто из вас на это способен...

🎮 КАК ИГРАТЬ:
Пишите мне сообщения и пытайтесь меня впечатлить.

Обращаться ко мне можно:
• Ответом на МОЁ сообщение (reply)
• Командой {config.COMMAND_PREFIX} твой_текст
• Упоминанием моего имени ({config.BOT_NAME}) в сообщении

⚠️ ПРАВИЛА (Medium Mode):
- Если будете хамить — сначала предупрежу, потом кину в игнор.
- Если будете молчать больше {int(config.CHECK_INTERVAL/60)} минут — я уйду.
- Игра идет максимум час. Если не успеете — ваши проблемы.

🏆 ПОБЕДА:
Когда я пойму, что влюбилась в кого-то из вас — скажу это сама и назову имя победителя. Игра закончится.

Если вы будете молчать больше {int(config.CHECK_INTERVAL/60)} минут — я уйду (закончу игру).
Сами виноваты, придется начинать заново 🤷‍♀️

Ну что, кто первый решится? Или все ссыкуны? 😈"""

    else:
        # Текст для СЛОЖНОЙ сложности
        intro_message = f"""Ну здарова, пацаны 👋

Я {config.BOT_NAME}, я {config.BOT_AGE}, из {config.BOT_CITY}. Слышала, вы тут типа хотите в меня влюбиться? 😏 Ха, посмотрим, кто из вас на это способен...

🎮 КАК ИГРАТЬ:
Пишите мне сообщения и пытайтесь меня впечатлить. Но учтите — я не из лёгких. Терпеть не могу тупые подкаты типа "привет красотка" 🤮

Обращаться ко мне можно:
• Ответом на МОЁ сообщение (reply)
• Командой {config.COMMAND_PREFIX} твой_текст
• Упоминанием моего имени ({config.BOT_NAME}) в сообщении

⚠️ ПРАВИЛА (Hard Mode):
- Сначала ПОЗНАКОМЬСЯ, а потом подкатывай (это важно, блять!)
- Будь оригинальным, я ненавижу шаблоны
- Умей шутить и не бойся быть дерзким
- Не обижайся на мой острый язык — я такая 💅

🏆 ПОБЕДА:
Когда я пойму, что влюбилась в кого-то из вас — скажу это сама и назову имя победителя. Игра закончится.

Если вы будете молчать больше {int(config.CHECK_INTERVAL/60)} минут — я уйду (закончу игру).
Сами виноваты, придется начинать заново 🤷‍♀️

Ну что, кто первый решится? Или все ссыкуны? 😈"""

    await context.bot.send_message(chat_id, intro_message)
    
    # Сохраняем в историю
    db.add_conversation(chat_id, "assistant", intro_message)
    
    # Останавливаем старую задачу проверки, если есть
    if chat_id in active_games:
        active_games[chat_id]['check_task'].cancel()
        del active_games[chat_id]
    
    # Запускаем фоновую проверку игры
    check_task = asyncio.create_task(check_game_progress(context, chat_id))
    active_games[chat_id] = {
        'check_task': check_task,
        'last_check': datetime.now()
    }
    
    logger.info(f"Game started in chat {chat_id} with difficulty {difficulty}")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка сообщений"""
    if not update.message or not update.message.text:
        return
    
    chat_id = update.effective_chat.id
    chat_type = update.effective_chat.type
    
    # Игнорируем личные сообщения
    if chat_type == "private":
        return
    
    message_text = update.message.text
    user = update.effective_user
    user_id = user.id
    username = user.username or ""
    first_name = user.first_name or "Аноним"
    
    # Проверяем активна ли игра
    game_active = db.is_game_active(chat_id)

    # Проверяем текстовые команды запуска
    is_trigger = False
    message_lower = message_text.lower().strip()
    for trigger in config.START_TRIGGERS:
        if trigger in message_lower:
            is_trigger = True
            break
    
    if is_trigger and not game_active:
        # Вместо прямого запуска вызываем команду старт (для выбора сложности)
        await start(update, context)
        return
    
    # Если игра не активна и это не триггер старта - игнорируем
    if not game_active:
        return
    
    should_process = False
    
    if update.message.reply_to_message and update.message.reply_to_message.from_user.id == context.bot.id:
        should_process = True
        message_text = update.message.text
    elif message_text.startswith(config.COMMAND_PREFIX):
        should_process = True
        message_text = message_text[len(config.COMMAND_PREFIX):].strip()
        if not message_text:
            await update.message.reply_text("Ну и что ты хотел сказать? Пусто же 🤨")
            return
    elif config.BOT_NAME.lower() in message_text.lower():
        should_process = True
    elif is_trigger and game_active:
        should_process = True
    
    if not should_process:
        return
    
    # Создаем или получаем лок для чата
    if chat_id not in chat_locks:
        chat_locks[chat_id] = asyncio.Lock()

    # Используем лок, чтобы обрабатывать сообщения по очереди в рамках одного чата
    # Это предотвращает поломку контекста при одновременных запросах
    async with chat_locks[chat_id]:
        # Снова проверяем активность игры внутри лока (на случай если она закончилась пока ждали)
        if not db.is_game_active(chat_id):
            return

        db.add_participant_message(chat_id, user_id, username, first_name, message_text)
        
        conversation_history = db.get_conversation_history(chat_id)
        participant_messages = db.get_participant_messages(chat_id, user_id)
        all_participants = db.get_participants(chat_id)
        
        # Получаем сложность текущей игры
        difficulty = db.get_game_difficulty(chat_id)
        
        # Получаем ответ от AI
        user_display_name = f"{first_name}" + (f" (@{username})" if username else "")
        ai_response = await ai.get_response(
            message_text,
            conversation_history,
            user_display_name,
            len(participant_messages),
            all_participants,
            difficulty
        )
        
        if ai_response.strip() == "ИГНОР":
            logger.info(f"AI decided to ignore message from {user_display_name} in chat {chat_id}")
            return
        
        db.add_conversation(chat_id, "user", f"{user_display_name}: {message_text}")
        db.add_conversation(chat_id, "assistant", ai_response)
        
        await update.message.reply_text(ai_response)

        # --- МГНОВЕННАЯ ПРОВЕРКА ПОБЕДЫ ПО ОТВЕТУ ---
        # Проверяем ключевые фразы из промпта ("я в тебя влюбилась")
        ai_resp_lower = ai_response.lower()
        if "я в тебя влюбилась" in ai_resp_lower and "хочу быть с тобой" in ai_resp_lower:
            
            winner_display = f"{first_name}" + (f" (@{username})" if username else "")
            
            system_msg = f"""💕 ИГРА ОКОНЧЕНА! 💕

Всё... я влюбилась. Да, блять, ВЛЮБИЛАСЬ! Не могу поверить сама 😳

{winner_display} — ты победил(а)! Ты смог(ла) растопить моё сердце ❤️

Хочу быть с тобой 💋

Остальные — сорян, не повезло 🤷‍♀️

Чтобы начать новую игру, напишите /start, /alisa или "Алиса приходи"."""

            await context.bot.send_message(chat_id, system_msg)
            
            # Завершаем игру в БД
            db.end_game(chat_id, user_id, winner_display)
            
            # Останавливаем фоновую задачу
            if chat_id in active_games:
                active_games[chat_id]['check_task'].cancel()
                del active_games[chat_id]
            
            logger.info(f"Instant win triggered by keywords for {winner_display} in chat {chat_id}")
            return
    
    logger.info(f"Processed message from {user_display_name} in chat {chat_id}")

async def check_game_progress(context: ContextTypes.DEFAULT_TYPE, chat_id: int):
    """Фоновая задача для проверки прогресса игры и тайм-аута"""
    try:
        while db.is_game_active(chat_id):
            await asyncio.sleep(config.CHECK_INTERVAL)
            
            if not db.is_game_active(chat_id):
                break
            
            difficulty = db.get_game_difficulty(chat_id)
            
            # --- ПРОВЕРКА НА БЕЗДЕЙСТВИЕ (INACTIVITY) ---
            last_msg_time_str = db.get_last_message_time(chat_id)
            
            if last_msg_time_str:
                last_msg_time = datetime.fromisoformat(last_msg_time_str)
                silence_duration = (datetime.now() - last_msg_time).total_seconds()
                
                # Завершаем игру если участники молчат больше CHECK_INTERVAL
                if silence_duration > config.CHECK_INTERVAL + 30:
                    await end_game_inactivity(context, chat_id)
                    break
            
            # --- ПРОВЕРКА ОБЩЕГО ВРЕМЕНИ ---
            start_time_str = db.get_game_start_time(chat_id)
            if start_time_str:
                start_time = datetime.fromisoformat(start_time_str)
                total_elapsed = (datetime.now() - start_time).total_seconds()
                
                # Получаем MAX_GAME_DURATION в зависимости от сложности
                max_duration = config.get_max_game_duration(difficulty)
                
                # Если прошло максимальное время сессии - завершаем обязательно
                if total_elapsed >= max_duration:
                    await end_game_timeout(context, chat_id)
                    break
                
                # Периодически проверяем, не влюбилась ли Алиса (только после MIN_GAME_DURATION)
                if total_elapsed >= config.MIN_GAME_DURATION:
                    participants = db.get_participants(chat_id)
                    if len(participants) > 0 and participants[0]['message_count'] >= 3:
                        await check_for_winner(context, chat_id)
                        # Проверяем, не завершилась ли игра после check_for_winner
                        if not db.is_game_active(chat_id):
                            break
    
    except asyncio.CancelledError:
        logger.info(f"Game check task cancelled for chat {chat_id}")
    except Exception as e:
        logger.error(f"Error in check_game_progress for chat {chat_id}: {e}")

async def check_for_winner(context: ContextTypes.DEFAULT_TYPE, chat_id: int):
    """Проверка, есть ли победитель"""
    try:
        participants = db.get_participants(chat_id)
        all_messages = db.get_participant_messages(chat_id)
        difficulty = db.get_game_difficulty(chat_id)
        
        # AI решает (передаем сложность)
        decision = await ai.decide_winner(participants, all_messages, difficulty)
        
        if decision and decision.get('in_love'):
            winner_id = decision.get('winner_user_id')
            winner_name = decision.get('winner_name')
            reason = decision.get('reason', '')
            
            winner = next((p for p in participants if p['user_id'] == winner_id), None)
            if winner:
                winner_display = f"{winner['first_name']}" + (f" (@{winner['username']})" if winner['username'] else "")
                
                victory_message = f"""💕 ИГРА ОКОНЧЕНА! 💕

Всё... я влюбилась. Да, блять, ВЛЮБИЛАСЬ! Не могу поверить сама 😳

{winner_display} — ты победил(а)! Ты смог(ла) растопить моё сердце ❤️

{reason}

Хочу быть с тобой 💋

Остальные — сорян, не повезло 🤷‍♀️

Чтобы начать новую игру, напишите /start, /alisa или "Алиса приходи"."""

                await context.bot.send_message(chat_id, victory_message)
                db.end_game(chat_id, winner_id, winner_display)
                if chat_id in active_games:
                    active_games[chat_id]['check_task'].cancel()
                    del active_games[chat_id]
                logger.info(f"Game won by {winner_display} in chat {chat_id}")
    
    except Exception as e:
        logger.error(f"Error checking for winner in chat {chat_id}: {e}")

async def end_game_inactivity(context: ContextTypes.DEFAULT_TYPE, chat_id: int):
    try:
        inactivity_message = f"""🙄 Ой всё, скучно с вами.

Вы молчите уже целую вечность. Я не нанималась ждать вас тут вечно.
Пойду найду кого-нибудь поразговорчивее 💅

Игра окончена. Если захотите снова попробовать (и не тупить) — пишите /start, /alisa или "Алиса приходи"."""

        await context.bot.send_message(chat_id, inactivity_message)
        db.end_game(chat_id)
        if chat_id in active_games:
            del active_games[chat_id]
        logger.info(f"Game ended by inactivity in chat {chat_id}")
        
    except Exception as e:
        logger.error(f"Error ending game by inactivity in chat {chat_id}: {e}")

async def end_game_timeout(context: ContextTypes.DEFAULT_TYPE, chat_id: int):
    try:
        participants = db.get_participants(chat_id)
        difficulty = db.get_game_difficulty(chat_id)
        
        if len(participants) == 0:
            timeout_message = f"""⏰ ВРЕМЯ ВЫШЛО!

Ну и что это было? Никто даже не попытался... Скучно же, блять! 😤

Если хотите попробовать снова — напишите /start, /alisa или "Алиса приходи" 😏"""
        else:
            all_messages = db.get_participant_messages(chat_id)
            decision = await ai.decide_winner(participants, all_messages, difficulty)
            
            if decision and decision.get('in_love'):
                await check_for_winner(context, chat_id)
                return
            else:
                reason = decision.get('reason', 'Никто не впечатлил меня') if decision else 'Никто не впечатлил меня'
                timeout_message = f"""⏰ ВРЕМЯ ВЫШЛО!

Всё, ребят, игра окончена. И знаете что? Я ни в кого не влюбилась 💔

{reason}

Все были какие-то... скучные? Шаблонные? Не знаю. Но меня никто не зацепил 🤷‍♀️

Попробуйте ещё раз, может повезёт — /start, /alisa или "Алиса приходи" 😏"""
        
        await context.bot.send_message(chat_id, timeout_message)
        db.end_game(chat_id)
        if chat_id in active_games:
            del active_games[chat_id]
        logger.info(f"Game ended by timeout in chat {chat_id}")
    
    except Exception as e:
        logger.error(f"Error ending game by timeout in chat {chat_id}: {e}")

async def shutdown(application: Application):
    """Корректное завершение всех задач при остановке бота"""
    logger.info("Shutting down... cancelling active games.")
    if active_games:
        for chat_id, game_data in active_games.items():
            task = game_data['check_task']
            if not task.done():
                task.cancel()
        
        tasks = [g['check_task'] for g in active_games.values()]
        # Wait specifically for cancellations
        await asyncio.gather(*tasks, return_exceptions=True)
        logger.info(f"Cancelled {len(tasks)} active game tasks.")

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.error(f"Update {update} caused error {context.error}")

def main():
    if not config.TELEGRAM_BOT_TOKEN:
        logger.error("TELEGRAM_BOT_TOKEN not set!")
        return
    
    infrastructure.start_server()
    
    # Добавлен хук post_shutdown для корректного выхода
    application = Application.builder()\
        .token(config.TELEGRAM_BOT_TOKEN)\
        .post_shutdown(shutdown)\
        .build()
    
    # Хендлеры
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("alisa", start))
    application.add_handler(CommandHandler("help", help_command))
    
    application.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, on_new_chat_members))
    
    # Обработчик кнопок сложности
    application.add_handler(CallbackQueryHandler(difficulty_callback, pattern=r"^diff\|"))
    
    cmd_name = config.COMMAND_PREFIX.lstrip('/')
    application.add_handler(CommandHandler(cmd_name, handle_message))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    application.add_error_handler(error_handler)
    
    job_queue = application.job_queue
    if config.RENDER_APP_URL:
        job_queue.run_repeating(infrastructure.self_ping, interval=600, first=60)
    
    # Backup каждые 24 часа (опционально)
    # job_queue.run_repeating(infrastructure.backup_database, interval=86400, first=3600)
    
    logger.info("Bot started!")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()
