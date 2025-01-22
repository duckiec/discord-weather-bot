import sqlite3
import json
import logging
from typing import Dict, Any
from functools import lru_cache
from threading import Lock
import queue
import time  # Change this import
import threading
import concurrent.futures

logger = logging.getLogger('weatherbot')

DEFAULT_SETTINGS = {
    "units": "metric",
    "decimal_places": 2,
    "forecast_days": 3
}

class DatabaseManager:
    def __init__(self, db_file: str = "bot.db", pool_size: int = 10, cache_ttl: int = 3600):
        self.db_file = db_file
        self.pool_size = pool_size
        self.cache_ttl = cache_ttl
        self.lock = Lock()
        self._local = threading.local()
        self._access_times = {}
        self.init_database()
        self._executor = concurrent.futures.ThreadPoolExecutor(
            max_workers=pool_size,
            thread_name_prefix="db_worker"
        )
        self._write_lock = Lock()  # Separate lock for writes

    def _get_connection(self):
        """Get a thread-local connection with pragmas for better performance"""
        if not hasattr(self._local, 'connection'):
            conn = sqlite3.connect(self.db_file)
            conn.row_factory = sqlite3.Row
            # Performance optimizations
            conn.execute("PRAGMA journal_mode=WAL")  # Write-Ahead Logging
            conn.execute("PRAGMA synchronous=NORMAL")  # Faster with reasonable safety
            conn.execute("PRAGMA cache_size=-64000")  # 64MB cache
            conn.execute("PRAGMA temp_store=MEMORY")  # Store temp tables in memory
            self._local.connection = conn
        return self._local.connection

    def _close_connections(self):
        """Close the thread-local connection if it exists"""
        if hasattr(self._local, 'connection'):
            self._local.connection.close()
            del self._local.connection

    def init_database(self):
        """Initialize the database with required tables and indexes"""
        try:
            with sqlite3.connect(self.db_file) as conn:
                cursor = conn.cursor()
                
                # Drop existing table to recreate with new schema
                cursor.execute("DROP TABLE IF EXISTS server_settings")
                
                # Create table with new schema
                cursor.execute("""
                    CREATE TABLE server_settings (
                        guild_id TEXT PRIMARY KEY,
                        settings TEXT NOT NULL,
                        last_updated INTEGER NOT NULL DEFAULT (strftime('%s', 'now')),
                        last_accessed INTEGER NOT NULL DEFAULT (strftime('%s', 'now'))
                    )
                """)
                
                # Create indexes
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_last_updated ON server_settings(last_updated)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_last_accessed ON server_settings(last_accessed)")
                
                conn.commit()
                logger.info("Database initialized with new schema")
        except Exception as e:
            logger.error(f"Database initialization error: {e}")

    @lru_cache(maxsize=2000)  # Increase cache size
    def get_server_settings(self, guild_id: str) -> Dict[str, Any]:
        """Get settings with better caching"""
        try:
            future = self._executor.submit(self._get_server_settings_sync, guild_id)
            return future.result(timeout=1.0)  # 1 second timeout
        except Exception as e:
            logger.error(f"Error getting server settings: {e}")
            return DEFAULT_SETTINGS.copy()

    def _get_server_settings_sync(self, guild_id: str) -> Dict[str, Any]:
        """Synchronous implementation of get_server_settings"""
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT settings FROM server_settings WHERE guild_id = ?
        """, (guild_id,))
        result = cursor.fetchone()
        
        if result:
            return json.loads(result[0])
            
        # New server, create default settings
        settings_json = json.dumps(DEFAULT_SETTINGS)
        cursor.execute("""
            INSERT INTO server_settings (guild_id, settings)
            VALUES (?, ?)
        """, (guild_id, settings_json))
        conn.commit()
        return DEFAULT_SETTINGS.copy()

    def set_server_settings(self, guild_id: str, settings: Dict[str, Any]) -> bool:
        """Save settings for a specific server"""
        current_time = int(time.time())  # Use time.time() instead of time()
        retries = 3
        retry_delay = 0.1  # 100ms

        for attempt in range(retries):
            try:
                with self._write_lock:
                    conn = self._get_connection()
                    cursor = conn.cursor()
                    settings_json = json.dumps(settings)
                    cursor.execute("""
                        INSERT OR REPLACE INTO server_settings 
                        (guild_id, settings, last_updated, last_accessed)
                        VALUES (?, ?, ?, ?)
                    """, (guild_id, settings_json, current_time, current_time))
                    conn.commit()
                    
                    # Clear the cache for this guild_id
                    self.get_server_settings.cache_clear()
                    return True
            except sqlite3.OperationalError as e:
                if "database is locked" in str(e) and attempt < retries - 1:
                    time.sleep(retry_delay * (2 ** attempt))  # Use time.sleep instead of time.sleep
                    continue
                logger.error(f"Error saving server settings: {e}")
                return False
            except Exception as e:
                logger.error(f"Error saving server settings: {e}")
                return False
        return False

    def cleanup_inactive_servers(self, days_inactive: int = 30, days_old: int = 90):
        """Cleanup servers that haven't been accessed recently"""
        current_time = int(time.time())
        inactive_cutoff = current_time - (days_inactive * 86400)
        old_cutoff = current_time - (days_old * 86400)
        
        try:
            with self.lock:
                conn = self._get_connection()
                cursor = conn.cursor()
                # Delete servers that haven't been accessed recently or are very old
                cursor.execute("""
                    DELETE FROM server_settings 
                    WHERE last_accessed < ? OR last_updated < ?
                """, (inactive_cutoff, old_cutoff))
                conn.commit()
                
                # Clear the entire cache if any servers were deleted
                if cursor.rowcount > 0:
                    self.get_server_settings.cache_clear()
        except Exception as e:
            logger.error(f"Error cleaning up inactive servers: {e}")

    def __del__(self):
        """Cleanup connections when the object is destroyed"""
        self._close_connections()
