import os
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import urlparse

from peewee import (
    PostgresqlDatabase,
    Proxy,
    SqliteDatabase,
)

from auto_vpn.core.utils import setup_logger

logger = setup_logger(name="db.db")


class DatabaseInitializationError(Exception):
    """Custom exception for database initialization errors"""

    pass


class Database:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance.initialized = False
            cls._instance.proxy = Proxy()
        return cls._instance

    def init_db(self, db_url: str):
        """
        Initialize the database connection.

        Args:
            db_url: Database URL string
        Raises:
            DatabaseInitializationError: If database initialization fails
            ValueError: If database scheme is unsupported
        """
        try:
            logger.info(f"Initializing database with URL: {db_url}")
            parsed_url = urlparse(db_url)

            if parsed_url.scheme == "sqlite":
                pragmas = {
                    "foreign_keys": 1,
                    "journal_mode": "wal",
                    "cache_size": -1024 * 64,
                }
                path = (
                    parsed_url.path[1:]
                    if parsed_url.path.startswith("/")
                    else parsed_url.path
                )

                # Ensure directory exists before creating SQLite database
                self._ensure_sqlite_directory(path)

                try:
                    database = SqliteDatabase(path, pragmas=pragmas)
                    logger.info(f"Successfully initialized SQLite database at: {path}")
                except Exception as e:
                    error_msg = f"Failed to initialize SQLite database: {e!s}"
                    logger.error(error_msg)
                    raise DatabaseInitializationError(error_msg) from e

            elif parsed_url.scheme == "postgresql":
                try:
                    database = PostgresqlDatabase(
                        database=parsed_url.path.lstrip("/"),
                        user=parsed_url.username,
                        password=parsed_url.password,
                        host=parsed_url.hostname,
                        port=parsed_url.port or 5432,
                    )
                    logger.info(
                        f"Successfully initialized PostgreSQL database at: {parsed_url.hostname}"
                    )
                except Exception as e:
                    error_msg = f"Failed to initialize PostgreSQL database: {e!s}"
                    logger.error(error_msg)
                    raise DatabaseInitializationError(error_msg) from e
            else:
                error_msg = "Unsupported database scheme. Use 'sqlite' or 'postgresql'."
                logger.error(error_msg)
                raise ValueError(error_msg)

            self.proxy.initialize(database)
            self.db = database
            self.initialized = True

            # Handle migrations
            try:
                from peewee_migrate import Router

                router = Router(self.db)
                router.run()
                logger.info("Database migrations completed successfully")
            except Exception as e:
                error_msg = f"Error running migrations: {e!s}"
                logger.error(error_msg)
                raise DatabaseInitializationError(error_msg) from e

        except (DatabaseInitializationError, ValueError):
            # Re-raise these exceptions as they're already properly formatted
            raise
        except Exception as e:
            # Catch any other unexpected errors
            error_msg = f"Unexpected error during database initialization: {e!s}"
            logger.error(error_msg)
            raise DatabaseInitializationError(error_msg) from e

    def _ensure_sqlite_directory(self, path: str) -> None:
        """
        Ensure the directory for SQLite database exists.

        Args:
            path: The database file path
        Raises:
            DatabaseInitializationError: If directory creation fails
        """
        try:
            directory = os.path.dirname(path)
            if directory:
                Path(directory).mkdir(parents=True, exist_ok=True)
                logger.info(f"Ensured SQLite directory exists: {directory}")
        except Exception as e:
            error_msg = f"Failed to create SQLite directory: {e!s}"
            logger.error(error_msg)
            raise DatabaseInitializationError(error_msg) from e

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
