import logging
import threading
import asyncio
import aiohttp
import os
import datetime
from flask import Flask
from telegram.ext import ContextTypes
import config

# Настройка логгера
logger = logging.getLogger(__name__)

# Инициализация Flask
app = Flask(__name__)

@app.route('/')
def home():
    return "Bot is running!", 200

@app.route('/ping')
def ping():
    return "pong", 200

def run_web_server():
    """Запускает Flask сервер в отдельном потоке"""
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)

def start_server():
    t = threading.Thread(target=run_web_server, daemon=True)
    t.start()

# ========== ЗАДАЧИ JOB QUEUE ==========

async def self_ping(context: ContextTypes.DEFAULT_TYPE):
    """Пингует сам себя, чтобы Render не уснул"""
    url = f"{config.RENDER_APP_URL}/ping"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                logger.info(f"Self-ping status: {resp.status}")
    except Exception as e:
        logger.error(f"Self-ping error: {e}")

async def backup_database(context: ContextTypes.DEFAULT_TYPE):
    """Отправляет файл базы данных в чат для бэкапов"""
    chat_id = config.BACKUP_CHAT_ID
    db_path = config.DB_NAME
    
    if not chat_id:
        logger.warning("BACKUP_CHAT_ID not set in config.")
        return

    if not os.path.exists(db_path):
        logger.error(f"Database file {db_path} not found!")
        return

    try:
        now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with open(db_path, 'rb') as f:
            await context.bot.send_document(
                chat_id=chat_id,
                document=f,
                caption=f"📦 Автоматический бэкап базы данных\n📅 {now}",
                disable_notification=True
            )
        logger.info("Database backup sent successfully.")
    except Exception as e:
        logger.error(f"Error sending backup: {e}")