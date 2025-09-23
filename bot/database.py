import logging
import sqlite3
from datetime import datetime

logger = logging.getLogger(__name__)

class DatabaseManager:
    """Manages the SQLite database for historical candle data"""
    
    def __init__(self, db_file: str = "database.db"):
        self.db_file = db_file
        self.conn = None
        self.connect()
        self.create_table()
        
    def connect(self):
        """Connect to the SQLite database"""
        try:
            self.conn = sqlite3.connect(self.db_file)
            logger.info(f"Connected to database: {self.db_file}")
        except sqlite3.Error as e:
            logger.error(f"Database connection error: {e}")
            
    def create_table(self):
        """Create the candles table if it doesn't exist"""
        if not self.conn:
            return
            
        try:
            cursor = self.conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS candles (
                    epic TEXT NOT NULL,
                    timestamp DATETIME NOT NULL,
                    open REAL NOT NULL,
                    high REAL NOT NULL,
                    low REAL NOT NULL,
                    close REAL NOT NULL,
                    volume INTEGER,
                    PRIMARY KEY (epic, timestamp)
                )
            """)
            self.conn.commit()
            logger.info("Candles table created or already exists")
        except sqlite3.Error as e:
            logger.error(f"Error creating table: {e}")
            
    def store_candle(self, epic: str, candle: dict):
        """Store a single 5-minute candle"""
        if not self.conn:
            return
            
        try:
            cursor = self.conn.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO candles (epic, timestamp, open, high, low, close, volume)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                epic,
                datetime.fromisoformat(candle['timestamp']),
                candle['open'],
                candle['high'],
                candle['low'],
                candle['close'],
                candle.get('volume')
            ))
            self.conn.commit()
        except sqlite3.Error as e:
            logger.error(f"Error storing candle: {e}")
            
    def get_candles(self, epic: str, limit: int = 100) -> list:
        """Get the latest N candles for an epic"""
        if not self.conn:
            return []
            
        try:
            cursor = self.conn.cursor()
            cursor.execute("""
                SELECT * FROM candles 
                WHERE epic = ? 
                ORDER BY timestamp DESC 
                LIMIT ?
            """, (epic, limit))
            return cursor.fetchall()
        except sqlite3.Error as e:
            logger.error(f"Error getting candles: {e}")
            return []

    def close(self):
        """Close the database connection"""
        if self.conn:
            self.conn.close()
            logger.info("Database connection closed")

