import os
from typing import Optional

from app.config import settings
from app.models import Object, Device, Reading


class Database:
    def __init__(self, connection_string: Optional[str] = None):
        self.connection_string = connection_string or settings.DATABASE_URL
        self.is_sqlite = self.connection_string.startswith('sqlite:')
        
        if self.is_sqlite:
            import sqlite3
            self.driver = sqlite3
            self.db_path = self.connection_string[10:]
        else:
            import psycopg2
            from psycopg2.extras import RealDictCursor
            self.driver = psycopg2
            self.cursor_factory = RealDictCursor

    def connect(self):
        if self.is_sqlite:
            conn = self.driver.connect(self.db_path)
            conn.row_factory = self.driver.Row
            return conn
        else:
            return self.driver.connect(self.connection_string)

    def init_schema(self):
        with self.connect() as conn:
            if self.is_sqlite:
                self._init_schema_sqlite(conn)
            else:
                self._init_schema_postgres(conn)

    def _init_schema_sqlite(self, conn):
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS objects (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS devices (
                id INTEGER PRIMARY KEY,
                object_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                type TEXT,
                FOREIGN KEY (object_id) REFERENCES objects(id)
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS readings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                device_id INTEGER NOT NULL,
                timestamp TIMESTAMP NOT NULL,
                value REAL NOT NULL,
                status TEXT DEFAULT 'ok',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (device_id) REFERENCES devices(id)
            )
        """)
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_readings_device_timestamp 
            ON readings(device_id, timestamp DESC)
        """)
        conn.commit()

    def _init_schema_postgres(self, conn):
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS objects (
                    id INTEGER PRIMARY KEY,
                    name TEXT NOT NULL
                )
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS devices (
                    id INTEGER PRIMARY KEY,
                    object_id INTEGER NOT NULL,
                    name TEXT NOT NULL,
                    type TEXT,
                    FOREIGN KEY (object_id) REFERENCES objects(id)
                )
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS readings (
                    id SERIAL PRIMARY KEY,
                    device_id INTEGER NOT NULL,
                    timestamp TIMESTAMP NOT NULL,
                    value FLOAT NOT NULL,
                    status TEXT DEFAULT 'ok',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (device_id) REFERENCES devices(id)
                )
            """)
            cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_readings_device_timestamp 
                ON readings(device_id, timestamp DESC)
            """)
            conn.commit()

    def save_object(self, obj: Object):
        with self.connect() as conn:
            if self.is_sqlite:
                cur = conn.cursor()
                cur.execute(
                    "INSERT OR REPLACE INTO objects (id, name) VALUES (?, ?)",
                    (obj.id, obj.name),
                )
            else:
                with conn.cursor() as cur:
                    cur.execute(
                        "INSERT INTO objects (id, name) VALUES (%s, %s) "
                        "ON CONFLICT (id) DO UPDATE SET name = EXCLUDED.name",
                        (obj.id, obj.name),
                    )
            conn.commit()

    def save_device(self, device: Device):
        with self.connect() as conn:
            if self.is_sqlite:
                cur = conn.cursor()
                cur.execute(
                    "INSERT OR REPLACE INTO devices (id, object_id, name, type) VALUES (?, ?, ?, ?)",
                    (device.id, device.object_id, device.name, device.type),
                )
            else:
                with conn.cursor() as cur:
                    cur.execute(
                        "INSERT INTO devices (id, object_id, name, type) VALUES (%s, %s, %s, %s) "
                        "ON CONFLICT (id) DO UPDATE SET name = EXCLUDED.name, type = EXCLUDED.type",
                        (device.id, device.object_id, device.name, device.type),
                    )
            conn.commit()

    def save_reading(self, reading: Reading):
        with self.connect() as conn:
            if self.is_sqlite:
                cur = conn.cursor()
                cur.execute(
                    "INSERT INTO readings (device_id, timestamp, value, status) VALUES (?, ?, ?, ?)",
                    (reading.device_id, reading.timestamp, reading.value, reading.status),
                )
            else:
                with conn.cursor() as cur:
                    cur.execute(
                        "INSERT INTO readings (device_id, timestamp, value, status) VALUES (%s, %s, %s, %s)",
                        (reading.device_id, reading.timestamp, reading.value, reading.status),
                    )
            conn.commit()

    def get_last_reading(self, device_id: int) -> Optional[Reading]:
        with self.connect() as conn:
            if self.is_sqlite:
                cur = conn.cursor()
                cur.execute(
                    "SELECT device_id, timestamp, value, status FROM readings "
                    "WHERE device_id = ? ORDER BY timestamp DESC LIMIT 1",
                    (device_id,),
                )
            else:
                from psycopg2.extras import RealDictCursor
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    cur.execute(
                        "SELECT device_id, timestamp, value, status FROM readings "
                        "WHERE device_id = %s ORDER BY timestamp DESC LIMIT 1",
                        (device_id,),
                    )
            
            row = cur.fetchone()
            if row:
                return Reading(
                    device_id=row["device_id"],
                    timestamp=row["timestamp"],
                    value=row["value"],
                    status=row["status"],
                )
            return None


def get_database() -> Database:
    return Database()
