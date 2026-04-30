"""Async SQLite connection management using aiosqlite."""

import aiosqlite
from pathlib import Path


class Database:
    """Manages async SQLite connections."""

    def __init__(self, db_url: str = "sqlite:///evil_mentor.db") -> None:
        # Strip the 'sqlite:///' prefix to get the file path
        if db_url.startswith("sqlite:///"):
            self._db_path = db_url[len("sqlite:///"):]
        else:
            self._db_path = db_url
        self._connection: aiosqlite.Connection | None = None

    @property
    def db_path(self) -> str:
        return self._db_path

    async def connect(self) -> aiosqlite.Connection:
        """Open a connection to the SQLite database."""
        if self._connection is None:
            self._connection = await aiosqlite.connect(self._db_path)
            # Enable WAL mode for better concurrent read performance
            await self._connection.execute("PRAGMA journal_mode=WAL")
            # Enable foreign key enforcement
            await self._connection.execute("PRAGMA foreign_keys=ON")
            # Return rows as sqlite3.Row for dict-like access
            self._connection.row_factory = aiosqlite.Row
        return self._connection

    async def get_connection(self) -> aiosqlite.Connection:
        """Get the current connection, opening one if needed."""
        if self._connection is None:
            return await self.connect()
        return self._connection

    async def close(self) -> None:
        """Close the database connection."""
        if self._connection is not None:
            await self._connection.close()
            self._connection = None
