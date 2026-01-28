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
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS game_sessions (
                chat_id INTEGER PRIMARY KEY,
                is_active INTEGER DEFAULT 1,
                status TEXT DEFAULT 'waiting', -- waiting, playing, finished
                difficulty TEXT DEFAULT 'hard',
                initiator_id INTEGER,
                started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                ended_at TIMESTAMP,
                winner_user_id INTEGER,
                winner_name TEXT
            )
        ''')
        
        # Таблица для зарегистрированных участников игры
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS game_participants (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id INTEGER,
                user_id INTEGER,
                username TEXT,
                first_name TEXT,
                joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(chat_id, user_id),
                FOREIGN KEY (chat_id) REFERENCES game_sessions(chat_id)
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
        
        # Миграции для старых баз данных
        try:
            cursor.execute('ALTER TABLE game_sessions ADD COLUMN difficulty TEXT DEFAULT "hard"')
        except sqlite3.OperationalError:
            pass
            
        try:
            cursor.execute('ALTER TABLE game_sessions ADD COLUMN status TEXT DEFAULT "playing"')
        except sqlite3.OperationalError:
            pass
            
        try:
            cursor.execute('ALTER TABLE game_sessions ADD COLUMN initiator_id INTEGER')
        except sqlite3.OperationalError:
            pass
        
        conn.commit()
        conn.close()
    
    def init_game_session(self, chat_id: int, initiator_id: int, difficulty: str = "hard"):
        """Создать сессию игры в режиме ожидания (Лобби)"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        # Завершить предыдущую
        cursor.execute('UPDATE game_sessions SET is_active = 0, ended_at = CURRENT_TIMESTAMP WHERE chat_id = ? AND is_active = 1', (chat_id,))
        
        # Очистить старые данные
        cursor.execute('DELETE FROM participant_messages WHERE chat_id = ?', (chat_id,))
        cursor.execute('DELETE FROM conversation_history WHERE chat_id = ?', (chat_id,))
        cursor.execute('DELETE FROM game_participants WHERE chat_id = ?', (chat_id,))
        
        # Создаем или обновляем сессию
        cursor.execute('SELECT chat_id FROM game_sessions WHERE chat_id = ?', (chat_id,))
        exists = cursor.fetchone()
        
        if exists:
            cursor.execute('''
                UPDATE game_sessions 
                SET is_active = 1, status = 'waiting', difficulty = ?, initiator_id = ?, 
                    started_at = CURRENT_TIMESTAMP, ended_at = NULL, winner_user_id = NULL, winner_name = NULL
                WHERE chat_id = ?
            ''', (difficulty, initiator_id, chat_id,))
        else:
            cursor.execute('''
                INSERT INTO game_sessions (chat_id, is_active, status, difficulty, initiator_id) 
                VALUES (?, 1, 'waiting', ?, ?)
            ''', (chat_id, difficulty, initiator_id))
        
        conn.commit()
        conn.close()
        logger.info(f"Initialized lobby for chat {chat_id}, difficulty {difficulty}")

    def add_participant(self, chat_id: int, user_id: int, username: str, first_name: str) -> bool:
        """Добавить участника в игру. Возвращает True если добавлен, False если уже был."""
        conn = self.get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute('''
                INSERT INTO game_participants (chat_id, user_id, username, first_name)
                VALUES (?, ?, ?, ?)
            ''', (chat_id, user_id, username or "", first_name or "Аноним"))
            conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False
        finally:
            conn.close()

    def get_registered_participants(self, chat_id: int) -> List[Dict]:
        """Получить список зарегистрированных участников"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT user_id, username, first_name FROM game_participants WHERE chat_id = ?', (chat_id,))
        results = cursor.fetchall()
        conn.close()
        return [{'user_id': r[0], 'username': r[1], 'first_name': r[2]} for r in results]

    def is_participant(self, chat_id: int, user_id: int) -> bool:
        """Проверить, является ли пользователь участником"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT 1 FROM game_participants WHERE chat_id = ? AND user_id = ?', (chat_id, user_id))
        result = cursor.fetchone()
        conn.close()
        return bool(result)

    def set_game_started(self, chat_id: int):
        """Перевести игру в статус 'playing'"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("UPDATE game_sessions SET status = 'playing', started_at = CURRENT_TIMESTAMP WHERE chat_id = ? AND is_active = 1", (chat_id,))
        conn.commit()
        conn.close()

    def get_game_info(self, chat_id: int) -> Optional[Dict]:
        """Получить информацию о текущей игре"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT status, difficulty, initiator_id, is_active 
            FROM game_sessions 
            WHERE chat_id = ? AND is_active = 1
        ''', (chat_id,))
        result = cursor.fetchone()
        conn.close()
        if result:
            return {
                'status': result[0],
                'difficulty': result[1],
                'initiator_id': result[2],
                'is_active': result[3]
            }
        return None

    def is_game_active(self, chat_id: int) -> bool:
        """Проверить активна ли игра (в любом статусе)"""
        info = self.get_game_info(chat_id)
        return info is not None and info['is_active'] == 1

    def is_game_playing(self, chat_id: int) -> bool:
        """Проверить, идет ли сам процесс игры (статус playing)"""
        info = self.get_game_info(chat_id)
        return info is not None and info['is_active'] == 1 and info['status'] == 'playing'

    def get_game_difficulty(self, chat_id: int) -> str:
        info = self.get_game_info(chat_id)
        return info['difficulty'] if info else "hard"
    
    def end_game(self, chat_id: int, winner_user_id: Optional[int] = None, winner_name: Optional[str] = None):
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
    
    def get_participants_stats(self, chat_id: int) -> List[Dict]:
        """Статистика сообщений для промпта (только активные сообщения)"""
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
