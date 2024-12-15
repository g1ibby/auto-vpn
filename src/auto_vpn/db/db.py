from peewee import (
    SqliteDatabase,
    PostgresqlDatabase,
    Proxy,
)
from urllib.parse import urlparse
from contextlib import contextmanager
from auto_vpn.core.utils import setup_logger

logger = setup_logger(name="db.db")

class Database:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(Database, cls).__new__(cls)
            cls._instance.initialized = False
            cls._instance.proxy = Proxy() 
        return cls._instance

    def init_db(self, db_url: str = 'sqlite:///data_layer.db'):
        logger.info(f"Initializing database with URL: {db_url}")
        parsed_url = urlparse(db_url)
        
        if parsed_url.scheme == 'sqlite':
            pragmas = {
                'foreign_keys': 1,
                'journal_mode': 'wal',
                'cache_size': -1024 * 64,
            }
            path = parsed_url.path[1:] if parsed_url.path.startswith('/') else parsed_url.path
            database = SqliteDatabase(path, pragmas=pragmas)
        
        elif parsed_url.scheme == 'postgresql':
            database = PostgresqlDatabase(
                database=parsed_url.path.lstrip('/'),
                user=parsed_url.username,
                password=parsed_url.password,
                host=parsed_url.hostname,
                port=parsed_url.port or 5432,
            )
        else:
            raise ValueError("Unsupported database scheme. Use 'sqlite' or 'postgresql'.")

        self.proxy.initialize(database)
        self.db = database
        self.initialized = True

        # Replace create_tables with migration
        from peewee_migrate import Router
        router = Router(self.db)
 
        # Run all pending migrations
        try:
            router.run()
            logger.info("Database migrations completed successfully")
        except Exception as e:
            logger.error(f"Error running migrations: {e}")
            raise

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

