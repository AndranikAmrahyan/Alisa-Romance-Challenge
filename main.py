import logging
import asyncio
from datetime import datetime, timedelta, timezone
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
# {chat_id: {'task': asyncio.Task, 'type': 'lobby'|'game', 'lobby_msg_id': int}}
active_games = {} 

# Блокировки для чатов
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
    """Обработка выбора сложности -> Создание Лобби"""
    query = update.callback_query
    await query.answer()
    
    data = query.data.split("|")
    if len(data) != 3 or data[0] != "diff":
        return
        
    difficulty = data[1]
    initiator_id = int(data[2])
    
    if query.from_user.id != initiator_id:
        await query.answer("Не ты запускал, не тебе выбирать 😡", show_alert=True)
        return

    # Инициализируем Лобби в БД
    chat_id = update.effective_chat.id
    db.init_game_session(chat_id, initiator_id, difficulty)
    
    # Добавляем инициатора сразу как участника
    user = query.from_user
    db.add_participant(chat_id, user.id, user.username, user.first_name)
    
    if config.MAX_PLAYERS_PER_GAME == 1:
        diff_text = {"easy": "😇 Легкая", "medium": "😐 Средняя", "hard": "👿 Сложная"}.get(difficulty, difficulty)
        await query.edit_message_text(
            f"Выбрана сложность: <b>{diff_text}</b>. Режим одного игрока. Погнали! 🚀", 
            parse_mode=ParseMode.HTML,
            reply_markup=None
        )
        await start_game_logic(chat_id, context, difficulty)
        return

    # Запускаем задачу авто-отмены лобби (если долго не начинают)
    if chat_id in active_games:
        active_games[chat_id]['task'].cancel()
        
    lobby_task = asyncio.create_task(check_lobby_timeout(context, chat_id, initiator_id))
    
    # Сохраняем msg_id, чтобы потом его редактировать при отмене
    active_games[chat_id] = {
        'task': lobby_task,
        'type': 'lobby',
        'lobby_msg_id': query.message.message_id 
    }

    # Отправляем сообщение Лобби (здесь оно отредактируется из меню сложности)
    await update_lobby_message(update, context, chat_id, difficulty, initiator_id)

async def update_lobby_message(update: Update, context: ContextTypes.DEFAULT_TYPE, chat_id: int, difficulty: str, initiator_id: int, is_auto_start=False):
    """Обновляет сообщение лобби (или отправляет новое)"""
    participants = db.get_registered_participants(chat_id)
    count = len(participants)
    max_players = config.MAX_PLAYERS_PER_GAME
    
    diff_text = {"easy": "😇 Легкая", "medium": "😐 Средняя", "hard": "👿 Сложная"}.get(difficulty, difficulty)
    
    # Формируем список с ссылками (tg://openmessage)
    participants_list_text = "\n".join([
        f"- <a href='tg://openmessage?user_id={p['user_id']}'>{p['first_name']}</a>" 
        for p in participants
    ])

    # Определяем имя инициатора из списка участников
    initiator_name = "Неизвестный"
    for p in participants:
        if p['user_id'] == initiator_id:
            initiator_name = p['first_name']
            break
    
    text = (
        f"{initiator_name}, идёт подбор игроков...\n\n"
        f"📊 Сложность: <b>{diff_text}</b>\n"
        f"👥 Присоединились: <b>{count}/{max_players}</b>\n\n"
        f"Участники:\n{participants_list_text}\n\n"
    )
    
    if is_auto_start:
        text += "✅ Набор завершен! Запускаем игру..."
    else:
        text += f"<i>({max_players - count} чел. ещё могут стать участником в самом процессе игры, просто обращаясь к Алисе)</i>"
    
    # Кнопки
    keyboard = []
    
    if not is_auto_start:
        # Если еще есть места, показываем кнопку присоединиться
        if count < max_players:
            keyboard.append([InlineKeyboardButton("➕ Присоединиться", callback_data=f"lobby|join")])
        
        # Кнопка старта
        keyboard.append([InlineKeyboardButton("🚀 Начать игру", callback_data=f"lobby|start|{initiator_id}")])
        
        # Кнопка отмены (только для инициатора)
        keyboard.append([InlineKeyboardButton("❌ Отмена", callback_data=f"lobby|cancel|{initiator_id}")])
    
    reply_markup = InlineKeyboardMarkup(keyboard) if keyboard else None
    
    if update.callback_query:
        # Если это callback (нажатие кнопки), редактируем сообщение
        try:
            await update.callback_query.edit_message_text(text, reply_markup=reply_markup, parse_mode=ParseMode.HTML)
        except Exception as e:
            logger.warning(f"Error updating lobby message: {e}")
    else:
        # Если это первый вызов после команды
        msg = await context.bot.send_message(chat_id, text, reply_markup=reply_markup, parse_mode=ParseMode.HTML)
        # Если вдруг создалось новое (редкий кейс), обновим ID
        if chat_id in active_games:
            active_games[chat_id]['lobby_msg_id'] = msg.message_id

async def lobby_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка кнопок Лобби (Присоединиться / Начать / Отмена)"""
    query = update.callback_query
    
    data = query.data.split("|")
    action = data[1]
    chat_id = update.effective_chat.id
    user = query.from_user
    
    # Проверяем статус игры (должен быть waiting)
    game_info = db.get_game_info(chat_id)
    if not game_info or game_info['status'] != 'waiting':
        await query.answer("Игра уже началась или была отменена!", show_alert=True)
        try:
            await query.edit_message_reply_markup(None)
        except:
            pass
        return

    if action == "join":
        # Попытка добавить участника
        success = db.add_participant(chat_id, user.id, user.username, user.first_name)
        
        if not success:
            # Пользователь уже в базе
            await query.answer("Ты уже участвуешь, не тупи!", show_alert=True)
            return
        
        await query.answer("Ты в игре!")
        
        # Проверяем, набрался ли фулл
        participants = db.get_registered_participants(chat_id)
        if len(participants) >= config.MAX_PLAYERS_PER_GAME:
            # --- Авто-старт ---
            await update_lobby_message(update, context, chat_id, game_info['difficulty'], game_info['initiator_id'], is_auto_start=True)
            await start_game_logic(chat_id, context, game_info['difficulty'])
        else:
            # Обновляем сообщение лобби
            await update_lobby_message(update, context, chat_id, game_info['difficulty'], game_info['initiator_id'])

    elif action == "start":
        initiator_id = int(data[2])
        if user.id != initiator_id:
            await query.answer(f"{user.first_name}, только создатель лобби может запустить игру досрочно!", show_alert=True)
            return
        
        await query.answer("Погнали!")
        await query.edit_message_reply_markup(None) # Удаляем кнопки
        await start_game_logic(chat_id, context, game_info['difficulty'])
        
    elif action == "cancel":
        initiator_id = int(data[2])
        if user.id != initiator_id:
            await query.answer(f"{user.first_name}, только создатель лобби может отменить игру!", show_alert=True)
            return
        
        await query.answer("Отменено")
        await cancel_lobby(context, chat_id, "Инициатор отменил игру.")

async def cancel_lobby(context: ContextTypes.DEFAULT_TYPE, chat_id: int, reason: str):
    """Отмена лобби (очистка и уведомление)"""
    
    lobby_msg_id = None
    task_to_cancel = None

    # Сначала получаем данные и чистим словарь, чтобы не потерять ID сообщения
    if chat_id in active_games:
        lobby_msg_id = active_games[chat_id].get('lobby_msg_id')
        task_to_cancel = active_games[chat_id].get('task')
        del active_games[chat_id]
        
    # Обновляем БД (завершаем сессию)
    db.end_game(chat_id)
    
    text = f"🚫 <b>Набор игроков отменен.</b>\nПричина: {reason}"
    
    # Пытаемся отредактировать старое сообщение
    success_edit = False
    if lobby_msg_id:
        try:
            await context.bot.edit_message_text(
                chat_id=chat_id,
                message_id=lobby_msg_id,
                text=text,
                parse_mode=ParseMode.HTML,
                reply_markup=None # Удаляем кнопки
            )
            success_edit = True
        except Exception as e:
            logger.warning(f"Failed to edit lobby message on cancel: {e}")
            
    if not success_edit:
        await context.bot.send_message(chat_id, text, parse_mode=ParseMode.HTML)

    # Отменяем задачу, если она есть и это не текущая задача (чтобы не убить самого себя при timeout)
    if task_to_cancel and task_to_cancel != asyncio.current_task():
        task_to_cancel.cancel()

async def check_lobby_timeout(context: ContextTypes.DEFAULT_TYPE, chat_id: int, initiator_id: int):
    """Фоновая задача для проверки времени жизни лобби"""
    try:
        await asyncio.sleep(config.CHECK_INTERVAL)
        
        # Если мы здесь, значит игра все еще в статусе ожидания
        game_info = db.get_game_info(chat_id)
        if game_info and game_info['status'] == 'waiting':
             # Вызываем отмену с редактированием сообщения
             await cancel_lobby(context, chat_id, f"Истекло время ожидания ({int(config.CHECK_INTERVAL/60)} мин).")
             
    except asyncio.CancelledError:
        pass
    except Exception as e:
        logger.error(f"Error in lobby timeout check: {e}")

async def start_game_logic(chat_id: int, context: ContextTypes.DEFAULT_TYPE, difficulty: str):
    """Фактический запуск игры (после лобби)"""
    
    # Отменяем задачу лобби, если она есть
    if chat_id in active_games:
        task = active_games[chat_id].get('task')
        if task:
            task.cancel()
        # Удаляем запись лобби из активных игр
        del active_games[chat_id]
    
    # Переводим статус в playing
    db.set_game_started(chat_id)
    
    # Тексты интро
    if difficulty == "easy":
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
        # HARD
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
    
    # Запускаем фоновую проверку игры
    check_task = asyncio.create_task(check_game_progress(context, chat_id))
    active_games[chat_id] = {
        'task': check_task,
        'type': 'game'
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
    
    # --- ЛОГИКА ТРИГГЕРОВ СТАРТА ---
    is_trigger = False
    message_lower = message_text.lower().strip()
    for trigger in config.START_TRIGGERS:
        if trigger in message_lower:
            is_trigger = True
            break
            
    is_game_active = db.is_game_active(chat_id)
    
    # Если это триггер и игра НЕ идет -> запускаем меню старта
    if is_trigger and not is_game_active:
        await start(update, context)
        return

    # Если игра НЕ идет и это не старт -> игнорируем
    if not is_game_active:
        return

    # Если игра идет:
    # Если игра в статусе Waiting (Лобби), игнорируем текстовые сообщения
    game_info = db.get_game_info(chat_id)
    if game_info and game_info['status'] == 'waiting':
        return
    
    # Определяем, обращение ли это к боту
    should_process = False
    if update.message.reply_to_message and update.message.reply_to_message.from_user.id == context.bot.id:
        should_process = True
    elif message_text.startswith(config.COMMAND_PREFIX):
        should_process = True
        message_text = message_text[len(config.COMMAND_PREFIX):].strip()
        if not message_text:
            return
    elif config.BOT_NAME.lower() in message_text.lower():
        should_process = True
    elif is_trigger: # Триггеры во время игры считаются обращением
        should_process = True
    
    if not should_process:
        return
    
    # Создаем или получаем лок для чата
    if chat_id not in chat_locks:
        chat_locks[chat_id] = asyncio.Lock()

    async with chat_locks[chat_id]:
        # Снова проверяем активность игры (на случай гонки)
        if not db.is_game_active(chat_id):
            return

        # --- ПРОВЕРКА УЧАСТНИКА И АВТО-ВХОД ---
        if not db.is_participant(chat_id, user_id):
            # Проверяем количество мест
            participants = db.get_registered_participants(chat_id)
            if len(participants) < config.MAX_PLAYERS_PER_GAME:
                # Место есть - добавляем автоматически
                db.add_participant(chat_id, user_id, username, first_name)
            else:
                # Мест нет - отшиваем
                await update.message.reply_text(
                    f"🚫 {first_name}, мест в игре больше нет! Жди следующей игры."
                )
                return

        # Если участник (или только что стал им), обрабатываем сообщение
        db.add_participant_message(chat_id, user_id, username, first_name, message_text)
        
        conversation_history = db.get_conversation_history(chat_id)
        participant_messages = db.get_participant_messages(chat_id, user_id)
        participants_stats = db.get_participants_stats(chat_id)
        
        difficulty = db.get_game_difficulty(chat_id)
        
        user_display_name = f"{first_name}" + (f" (@{username})" if username else "")
        
        # Запрос к AI
        ai_response = await ai.get_response(
            message_text,
            conversation_history,
            user_display_name,
            len(participant_messages),
            participants_stats, 
            difficulty
        )

        # --- ОБРАБОТКА ОШИБКИ ЛИМИТОВ API ---
        if ai_response == "SYSTEM_OVERLOAD_LIMITS":
            await context.bot.send_message(
                chat_id, 
                "⚠️ <b>СИСТЕМНЫЙ СБОЙ</b>\n\nМои нейронные сети перегрелись (достигнут дневной лимит API). Я вынуждена уйти спать. Приходите завтра! 😴",
                parse_mode=ParseMode.HTML
            )
            db.end_game(chat_id)
            if chat_id in active_games:
                active_games[chat_id]['task'].cancel()
                del active_games[chat_id]
            return
        
        if ai_response.strip() == "ИГНОР":
            return
        
        db.add_conversation(chat_id, "user", f"{user_display_name}: {message_text}")
        db.add_conversation(chat_id, "assistant", ai_response)
        
        await update.message.reply_text(ai_response)

        # --- ПРОВЕРКА ПОБЕДЫ ---
        if "я в тебя влюбилась" in ai_response.lower() and "хочу быть с тобой" in ai_response.lower():
            
            winner_display = f"{first_name}" + (f" (@{username})" if username else "")
            
            system_msg = f"""💕 ИГРА ОКОНЧЕНА! 💕

Всё... я влюбилась. Да, блять, ВЛЮБИЛАСЬ! Не могу поверить сама 😳

{winner_display} — ты победил(а)! Ты смог(ла) растопить моё сердце ❤️

Хочу быть с тобой 💋

Остальные — сорян, не повезло 🤷‍♀️

Чтобы начать новую игру, напишите /start, /alisa или "Алиса приходи"."""

            await context.bot.send_message(chat_id, system_msg)
            db.end_game(chat_id, user_id, winner_display)
            if chat_id in active_games:
                active_games[chat_id]['task'].cancel()
                del active_games[chat_id]
            return

async def check_game_progress(context: ContextTypes.DEFAULT_TYPE, chat_id: int):
    """Фоновая задача для проверки прогресса игры и тайм-аута"""
    try:
        while db.is_game_active(chat_id):
            await asyncio.sleep(config.CHECK_INTERVAL)
            
            if not db.is_game_playing(chat_id):
                 continue

            if not db.is_game_active(chat_id):
                break
            
            difficulty = db.get_game_difficulty(chat_id)
            
            # --- ПРОВЕРКА НА БЕЗДЕЙСТВИЕ (INACTIVITY) ---
            last_msg_time_str = db.get_last_message_time(chat_id)
            
            if last_msg_time_str:
                # В БД (SQLite CURRENT_TIMESTAMP) время в UTC. 
                # datetime.now() возвращает локальное время сервера.
                # Используем timezone.utc для корректного сравнения.
                
                # Парсим время из БД как UTC-aware
                last_msg_time = datetime.fromisoformat(last_msg_time_str).replace(tzinfo=timezone.utc)
                
                # Текущее время тоже в UTC-aware
                now_utc = datetime.now(timezone.utc)
                
                silence_duration = (now_utc - last_msg_time).total_seconds()
                
                # Завершаем игру если участники молчат больше CHECK_INTERVAL
                if silence_duration > config.CHECK_INTERVAL + 30:
                    await end_game_inactivity(context, chat_id)
                    break
            
            # --- ПРОВЕРКА ОБЩЕГО ВРЕМЕНИ ---
            start_time_str = db.get_game_start_time(chat_id)
            if start_time_str:
                start_time = datetime.fromisoformat(start_time_str).replace(tzinfo=timezone.utc)
                now_utc = datetime.now(timezone.utc)
                
                total_elapsed = (now_utc - start_time).total_seconds()
                
                max_duration = config.get_max_game_duration(difficulty)
                
                if total_elapsed >= max_duration:
                    await end_game_timeout(context, chat_id)
                    break
                
                if total_elapsed >= config.MIN_GAME_DURATION:
                    # Проверка победителя (опционально)
                    stats = db.get_participants_stats(chat_id)
                    if len(stats) > 0 and stats[0]['message_count'] >= 3:
                        await check_for_winner(context, chat_id)
                        if not db.is_game_active(chat_id):
                            break
    
    except asyncio.CancelledError:
        logger.info(f"Game check task cancelled for chat {chat_id}")
    except Exception as e:
        logger.error(f"Error in check_game_progress for chat {chat_id}: {e}")

async def check_for_winner(context: ContextTypes.DEFAULT_TYPE, chat_id: int):
    """Проверка, есть ли победитель"""
    try:
        participants = db.get_registered_participants(chat_id)
        all_messages = db.get_participant_messages(chat_id)
        difficulty = db.get_game_difficulty(chat_id)
        
        decision = await ai.decide_winner(participants, all_messages, difficulty)
        
        if decision and decision.get('in_love'):
            winner_id = decision.get('winner_user_id')
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
                    active_games[chat_id]['task'].cancel()
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
            active_games[chat_id]['task'].cancel()
            del active_games[chat_id]
        logger.info(f"Game ended by inactivity in chat {chat_id}")
        
    except Exception as e:
        logger.error(f"Error ending game by inactivity in chat {chat_id}: {e}")

async def end_game_timeout(context: ContextTypes.DEFAULT_TYPE, chat_id: int):
    try:
        participants = db.get_registered_participants(chat_id)
        difficulty = db.get_game_difficulty(chat_id)
        
        if len(participants) == 0:
            timeout_message = f"""⏰ ВРЕМЯ ВЫШЛО!

Ну и что это было? Никто даже не попытался... Скучно же, блять! 😤

Если хотите попробовать снова — напишите /start, /alisa или "Алиса приходи" 😏"""
            await context.bot.send_message(chat_id, timeout_message)
            db.end_game(chat_id)

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
            active_games[chat_id]['task'].cancel()
            del active_games[chat_id]
        logger.info(f"Game ended by timeout in chat {chat_id}")
    
    except Exception as e:
        logger.error(f"Error ending game by timeout in chat {chat_id}: {e}")

async def shutdown(application: Application):
    """Корректное завершение всех задач при остановке бота"""
    logger.info("Shutting down... cancelling active games.")
    if active_games:
        tasks = [g['task'] for g in active_games.values()]
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.error(f"Update {update} caused error {context.error}")

def main():
    if not config.TELEGRAM_BOT_TOKEN:
        logger.error("TELEGRAM_BOT_TOKEN not set!")
        return
    
    infrastructure.start_server()
    
    application = Application.builder()\
        .token(config.TELEGRAM_BOT_TOKEN)\
        .post_shutdown(shutdown)\
        .build()
    
    # Хендлеры
    application.add_handler(CommandHandler(["start", "alisa"], start))
    application.add_handler(CommandHandler("help", help_command))
    
    application.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, on_new_chat_members))
    
    # Обработчик кнопок сложности
    application.add_handler(CallbackQueryHandler(difficulty_callback, pattern=r"^diff\|"))
    # Обработчик кнопок лобби (новый)
    application.add_handler(CallbackQueryHandler(lobby_callback, pattern=r"^lobby\|"))
    
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
