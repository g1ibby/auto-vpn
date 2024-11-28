from peewee import (
    SqliteDatabase,
)
from contextlib import contextmanager

class Database:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(Database, cls).__new__(cls)
            cls._instance.initialized = False
            cls._instance.db = SqliteDatabase(None)
        return cls._instance

    def init_db(self, database_path: str ='data_layer.db'):
        pragmas = {
            'foreign_keys': 1,
            'journal_mode': 'wal',
            'cache_size': -1024 * 64,
        }
        self.db.init(database_path, pragmas=pragmas)
        self.initialized = True
        
        from auto_vpn.db.models import BaseModel, Server, VPNPeer, Setting
        self.db.create_tables([Server, VPNPeer, Setting])

    @contextmanager
    def connection(self):
        if not self.initialized:
            raise RuntimeError("Database not initialized. Call init_db first.")
        
        # Check if connection is already open
        if not self.db.is_closed():
            # Use existing connection
            yield
        else:
            # Open new connection
            try:
                self.db.connect()
                yield
            finally:
                if not self.db.is_closed():
                    self.db.close()

db_instance = Database()

