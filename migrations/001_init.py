"""Peewee migrations -- 001_init.py."""

from contextlib import suppress

import peewee as pw
from peewee_migrate import Migrator

with suppress(ImportError):
    pass


def migrate(migrator: Migrator, database: pw.Database, *, fake=False):  # noqa: ARG001
    """Write your migrations here."""

    # Determine the appropriate datetime type based on the database
    if isinstance(database, pw.PostgresqlDatabase):
        datetime_type = "TIMESTAMP"
    else:
        datetime_type = "DATETIME"

    # Setting table
    migrator.sql(
        """
        CREATE TABLE "setting" (
            "id" SERIAL PRIMARY KEY,
            "key" VARCHAR(255) NOT NULL,
            "value" TEXT NOT NULL,
            "type" VARCHAR(255) NOT NULL
        )
    """
        if isinstance(database, pw.PostgresqlDatabase)
        else """
        CREATE TABLE "setting" (
            "id" INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
            "key" VARCHAR(255) NOT NULL,
            "value" TEXT NOT NULL,
            "type" VARCHAR(255) NOT NULL
        )
    """
    )

    migrator.sql('CREATE UNIQUE INDEX "setting_key" ON "setting" ("key")')

    # Server table
    migrator.sql(
        f"""
        CREATE TABLE "server" (
            "id" SERIAL PRIMARY KEY,
            "provider" VARCHAR(255) NOT NULL,
            "project_name" VARCHAR(255) NOT NULL,
            "ip_address" VARCHAR(255) NOT NULL,
            "username" VARCHAR(255) NOT NULL,
            "ssh_private_key" TEXT NOT NULL,
            "location" VARCHAR(255) NOT NULL,
            "stack_state" TEXT NOT NULL,
            "server_type" VARCHAR(255) NOT NULL,
            "created_at" {datetime_type} NOT NULL
        )
    """
        if isinstance(database, pw.PostgresqlDatabase)
        else f"""
        CREATE TABLE "server" (
            "id" INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
            "provider" VARCHAR(255) NOT NULL,
            "project_name" VARCHAR(255) NOT NULL,
            "ip_address" VARCHAR(255) NOT NULL,
            "username" VARCHAR(255) NOT NULL,
            "ssh_private_key" TEXT NOT NULL,
            "location" VARCHAR(255) NOT NULL,
            "stack_state" TEXT NOT NULL,
            "server_type" VARCHAR(255) NOT NULL,
            "created_at" {datetime_type} NOT NULL
        )
    """
    )

    migrator.sql('CREATE UNIQUE INDEX "server_ip_address" ON "server" ("ip_address")')

    # VPNPeer table
    migrator.sql(
        f"""
        CREATE TABLE "vpnpeer" (
            "id" SERIAL PRIMARY KEY,
            "server_id" INTEGER NOT NULL,
            "peer_name" VARCHAR(255) NOT NULL,
            "public_key" TEXT NOT NULL,
            "wireguard_config" TEXT NOT NULL,
            "created_at" {datetime_type} NOT NULL,
            FOREIGN KEY ("server_id") REFERENCES "server" ("id") ON DELETE CASCADE
        )
    """
        if isinstance(database, pw.PostgresqlDatabase)
        else f"""
        CREATE TABLE "vpnpeer" (
            "id" INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
            "server_id" INTEGER NOT NULL,
            "peer_name" VARCHAR(255) NOT NULL,
            "public_key" TEXT NOT NULL,
            "wireguard_config" TEXT NOT NULL,
            "created_at" {datetime_type} NOT NULL,
            FOREIGN KEY ("server_id") REFERENCES "server" ("id") ON DELETE CASCADE
        )
    """
    )

    migrator.sql('CREATE INDEX "vpnpeer_server_id" ON "vpnpeer" ("server_id")')
    migrator.sql(
        'CREATE UNIQUE INDEX "vpnpeer_server_id_peer_name" ON "vpnpeer" ("server_id", "peer_name")'
    )


def rollback(migrator: Migrator, database: pw.Database, *, fake=False):  # noqa: ARG001
    """Write your rollback migrations here."""
    migrator.sql('DROP TABLE IF EXISTS "vpnpeer"')
    migrator.sql('DROP TABLE IF EXISTS "server"')
    migrator.sql('DROP TABLE IF EXISTS "setting"')
