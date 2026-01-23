import os
from dotenv import load_dotenv

load_dotenv()

# Telegram Bot Token
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

# Groq API (бесплатный AI)
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"

# OpenRouter API
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
OPENROUTER_API_URL = "https://openrouter.ai/api/v1/chat/completions"

# Render настройки
RENDER_APP_URL = os.getenv("RENDER_APP_URL", "")
BACKUP_CHAT_ID = os.getenv("BACKUP_CHAT_ID", "")

# База данных
DB_NAME = "bot_data.db"

# Персонаж бота
BOT_NAME = "Алиса"
BOT_AGE = "взрослая"  # Никогда не говорит точный возраст
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
MIN_GAME_DURATION = 300   # 5 минут (чтобы AI успел узнать контекст)

# MAX_GAME_DURATION в зависимости от сложности
MAX_GAME_DURATION_HARD = 3600    # 1 час для сложного режима
MAX_GAME_DURATION_MEDIUM = 1800  # 30 минут для среднего режима
MAX_GAME_DURATION_EASY = 900     # 15 минут для легкого режима

CHECK_INTERVAL = 300      # Проверка каждые 5 минут

# Функция для получения MAX_GAME_DURATION в зависимости от сложности
def get_max_game_duration(difficulty: str) -> int:
    if difficulty == "easy":
        return MAX_GAME_DURATION_EASY
    elif difficulty == "medium":
        return MAX_GAME_DURATION_MEDIUM
    else:  # hard
        return MAX_GAME_DURATION_HARD

# Настройки AI
GROQ_AI_MODEL = "llama-3.3-70b-versatile"  # Groq бесплатная модель
OPENROUTER_AI_MODEL = "meta-llama/llama-3.3-70b-instruct:free"

AI_MAX_TOKENS = 400
AI_TEMPERATURE = 0.95  # Чуть повысил для "живости"

# Флаг: может ли Алиса обижаться и игнорировать (True - может, False - нет)
ENABLE_AI_IGNORE = False
