import sqlite3
import json
import logging
from typing import Optional, List, Dict
from datetime import datetime
import config

logger = logging.getLogger(__name__)

class Database:
    def __init__(self):
        self.db_name = config.DB_NAME
        self.init_db()
    
    def get_connection(self):
        return sqlite3.connect(self.db_name)
    
    def init_db(self):
        """Инициализация базы данных"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        # Таблица для игровых сессий
        # Добавлено поле difficulty
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS game_sessions (
                chat_id INTEGER PRIMARY KEY,
                is_active INTEGER DEFAULT 1,
                difficulty TEXT DEFAULT 'hard',
                started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                ended_at TIMESTAMP,
                winner_user_id INTEGER,
                winner_name TEXT
            )
        ''')
        
        # Таблица для сообщений участников
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS participant_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id INTEGER,
                user_id INTEGER,
                username TEXT,
                first_name TEXT,
                message TEXT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (chat_id) REFERENCES game_sessions(chat_id)
            )
        ''')
        
        # Таблица для истории разговора (для AI контекста)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS conversation_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id INTEGER,
                role TEXT,
                content TEXT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (chat_id) REFERENCES game_sessions(chat_id)
            )
        ''')
        
        # Миграция: проверяем, есть ли колонка difficulty, если нет - добавляем (для старых БД)
        try:
            cursor.execute('SELECT difficulty FROM game_sessions LIMIT 1')
        except sqlite3.OperationalError:
            cursor.execute('ALTER TABLE game_sessions ADD COLUMN difficulty TEXT DEFAULT "hard"')
            logger.info("Added 'difficulty' column to game_sessions")
        
        conn.commit()
        conn.close()
    
    def start_game(self, chat_id: int, difficulty: str = "hard"):
        """Начать новую игру с указанной сложностью"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        # Завершить предыдущую игру если есть
        cursor.execute('UPDATE game_sessions SET is_active = 0, ended_at = CURRENT_TIMESTAMP WHERE chat_id = ? AND is_active = 1', (chat_id,))
        
        # Удалить старые данные
        cursor.execute('DELETE FROM participant_messages WHERE chat_id = ?', (chat_id,))
        cursor.execute('DELETE FROM conversation_history WHERE chat_id = ?', (chat_id,))
        
        # Проверяем существует ли запись для этого чата
        cursor.execute('SELECT chat_id FROM game_sessions WHERE chat_id = ?', (chat_id,))
        exists = cursor.fetchone()
        
        if exists:
            # Обновляем существующую запись
            cursor.execute('''
                UPDATE game_sessions 
                SET is_active = 1, difficulty = ?, started_at = CURRENT_TIMESTAMP, ended_at = NULL, winner_user_id = NULL, winner_name = NULL
                WHERE chat_id = ?
            ''', (difficulty, chat_id,))
        else:
            # Создаем новую запись
            cursor.execute('INSERT INTO game_sessions (chat_id, is_active, difficulty) VALUES (?, 1, ?)', (chat_id, difficulty))
        
        conn.commit()
        conn.close()
        logger.info(f"Started new game for chat {chat_id} with difficulty {difficulty}")
    
    def is_game_active(self, chat_id: int) -> bool:
        """Проверить активна ли игра"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT is_active FROM game_sessions WHERE chat_id = ? ORDER BY started_at DESC LIMIT 1', (chat_id,))
        result = cursor.fetchone()
        conn.close()
        return result and result[0] == 1

    def get_game_difficulty(self, chat_id: int) -> str:
        """Получить сложность текущей игры"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT difficulty FROM game_sessions WHERE chat_id = ? AND is_active = 1', (chat_id,))
        result = cursor.fetchone()
        conn.close()
        return result[0] if result else "hard"
    
    def end_game(self, chat_id: int, winner_user_id: Optional[int] = None, winner_name: Optional[str] = None):
        """Завершить игру"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE game_sessions 
            SET is_active = 0, ended_at = CURRENT_TIMESTAMP, winner_user_id = ?, winner_name = ?
            WHERE chat_id = ? AND is_active = 1
        ''', (winner_user_id, winner_name, chat_id))
        conn.commit()
        conn.close()
        logger.info(f"Ended game for chat {chat_id}, winner: {winner_name}")
    
    def add_participant_message(self, chat_id: int, user_id: int, username: str, first_name: str, message: str):
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO participant_messages (chat_id, user_id, username, first_name, message)
            VALUES (?, ?, ?, ?, ?)
        ''', (chat_id, user_id, username or "", first_name or "Аноним", message))
        conn.commit()
        conn.close()
    
    def get_participant_messages(self, chat_id: int, user_id: Optional[int] = None) -> List[Dict]:
        conn = self.get_connection()
        cursor = conn.cursor()
        if user_id:
            cursor.execute('''
                SELECT user_id, username, first_name, message, timestamp 
                FROM participant_messages 
                WHERE chat_id = ? AND user_id = ?
                ORDER BY timestamp
            ''', (chat_id, user_id))
        else:
            cursor.execute('''
                SELECT user_id, username, first_name, message, timestamp 
                FROM participant_messages 
                WHERE chat_id = ?
                ORDER BY timestamp
            ''', (chat_id,))
        results = cursor.fetchall()
        conn.close()
        return [
            {'user_id': r[0], 'username': r[1], 'first_name': r[2], 'message': r[3], 'timestamp': r[4]}
            for r in results
        ]
    
    def get_participants(self, chat_id: int) -> List[Dict]:
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT DISTINCT user_id, username, first_name, COUNT(*) as message_count
            FROM participant_messages 
            WHERE chat_id = ?
            GROUP BY user_id
            ORDER BY message_count DESC
        ''', (chat_id,))
        results = cursor.fetchall()
        conn.close()
        return [
            {'user_id': r[0], 'username': r[1], 'first_name': r[2], 'message_count': r[3]}
            for r in results
        ]
    
    def add_conversation(self, chat_id: int, role: str, content: str):
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO conversation_history (chat_id, role, content)
            VALUES (?, ?, ?)
        ''', (chat_id, role, content))
        conn.commit()
        conn.close()
    
    def get_conversation_history(self, chat_id: int, limit: int = 50) -> List[Dict]:
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT role, content, timestamp 
            FROM conversation_history 
            WHERE chat_id = ?
            ORDER BY timestamp DESC
            LIMIT ?
        ''', (chat_id, limit))
        results = cursor.fetchall()
        conn.close()
        return [{'role': r[0], 'content': r[1], 'timestamp': r[2]} for r in reversed(results)]
    
    def get_game_start_time(self, chat_id: int) -> Optional[str]:
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT started_at FROM game_sessions WHERE chat_id = ? AND is_active = 1', (chat_id,))
        result = cursor.fetchone()
        conn.close()
        return result[0] if result else None

    def get_last_message_time(self, chat_id: int) -> Optional[str]:
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT timestamp FROM participant_messages WHERE chat_id = ? ORDER BY timestamp DESC LIMIT 1', (chat_id,))
        result = cursor.fetchone()
        if not result:
            cursor.execute('SELECT started_at FROM game_sessions WHERE chat_id = ? AND is_active = 1', (chat_id,))
            result = cursor.fetchone()
        conn.close()
        return result[0] if result else None