"""Peewee migrations -- 002_add_server_fields.py."""
from contextlib import suppress
import peewee as pw
from peewee_migrate import Migrator

with suppress(ImportError):
    import playhouse.postgres_ext as pw_pext

def migrate(migrator: Migrator, database: pw.Database, *, fake=False):
    """Write your migrations here."""
    
    # Add country column
    migrator.sql("""
        ALTER TABLE "server" 
        ADD COLUMN "country" VARCHAR(255) NOT NULL DEFAULT ''
    """)
    
    # Add price_per_month column
    if isinstance(database, pw.PostgresqlDatabase):
        migrator.sql("""
            ALTER TABLE "server" 
            ADD COLUMN "price_per_month" DOUBLE PRECISION NULL
        """)
    else:
        migrator.sql("""
            ALTER TABLE "server" 
            ADD COLUMN "price_per_month" FLOAT NULL
        """)

def rollback(migrator: Migrator, database: pw.Database, *, fake=False):
    """Write your rollback migrations here."""
    
    # Drop the new columns
    migrator.sql("""
        ALTER TABLE "server" DROP COLUMN "country"
    """)
    
    migrator.sql("""
        ALTER TABLE "server" DROP COLUMN "price_per_month"
    """)
