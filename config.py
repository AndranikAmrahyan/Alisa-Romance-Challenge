import os
from dotenv import load_dotenv

load_dotenv()

# Telegram Bot Token
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

# OpenRouter API Key (ЛУЧШИЙ ВАРИАНТ!)
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")

# Render настройки
RENDER_APP_URL = os.getenv("RENDER_APP_URL", "")
BACKUP_CHAT_ID = os.getenv("BACKUP_CHAT_ID", "")

# База данных
DB_NAME = "bot_data.db"

# Персонаж бота
BOT_NAME = "Алиса"
BOT_AGE = "взрослая"
BOT_COUNTRY = "Россия"
BOT_CITY = "Москвы"

# Команда для обращения к боту
COMMAND_PREFIX = "/say"

# Текстовые команды запуска
START_TRIGGERS = [
    "алиса приходи",
    "алиса давай играть",
    "алиса начнем",
    "алиса го играть",
    "алиса старт",
    "алиса выходи"
]

# Тайминги игры (в секундах)
MIN_GAME_DURATION = 300

MAX_GAME_DURATION_HARD = 3600
MAX_GAME_DURATION_MEDIUM = 1800
MAX_GAME_DURATION_EASY = 900

CHECK_INTERVAL = 300

def get_max_game_duration(difficulty: str) -> int:
    if difficulty == "easy":
        return MAX_GAME_DURATION_EASY
    elif difficulty == "medium":
        return MAX_GAME_DURATION_MEDIUM
    else:
        return MAX_GAME_DURATION_HARD
