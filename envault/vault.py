from pathlib import Path
from sqlcipher3 import dbapi2 as sqlite

import mimetypes


class VaultDB:
    def __init__(self, path: Path, password: str):
        self.path = path

        self._connection = sqlite.connect(path.as_posix())
        self._connection.execute(f"PRAGMA key = {password.replace("'", "''")};")

        self._connection.execute("SELECT count(*) FROM sqlite_master;").fetchone()
        self.__create_tables()

        self._files_cache = None

    def __create_tables(self):
        self._connection.execute("""
            CREATE TABLE IF NOT EXISTS files (
                path TEXT PRIMARY KEY,
                mime_type TEXT NOT NULL,
                data BLOB NOT NULL
            );
        """)
        self._connection.commit()

    def read_file(self, internal_path: Path) -> bytes:
        cursor = self._connection.execute(
            "SELECT data FROM files WHERE path = ?",
            (internal_path.as_posix(),),
        )

        row = cursor.fetchone()

        if row is None:
            raise FileNotFoundError(internal_path)

        return row[0]

    def add_file(self, internal_path: Path, data: bytes):
        mime_type, _ = mimetypes.guess_type(internal_path.name)
        mime_type = mime_type or "application/octet-stream"

        self._connection.execute(
            """
            INSERT OR REPLACE INTO files(path, mime_type, data)
            VALUES (?, ?, ?)
            """,
            (
                internal_path.as_posix(),
                mime_type,
                sqlite.Binary(data),
            ),
        )

        self._connection.commit()
        self._files_cache = None

    def remove_file(self, internal_path: Path):
        self._connection.execute(
            "DELETE FROM files WHERE path = ?",
            (internal_path.as_posix(),),
        )

        self._connection.commit()
        self._files_cache = None

    def rename_file(self, internal_path: Path, new_path: Path):
        self._connection.execute(
            "UPDATE files SET path = ? WHERE path = ?",
            (
                new_path.as_posix(),
                internal_path.as_posix(),
            ),
        )

        self._connection.commit()
        self._files_cache = None

    def get_files(self) -> list[Path]:
        if not self._files_cache is None:
            return self._files_cache

        cursor = self._connection.execute("SELECT path FROM files ORDER BY path")
        self._files_cache = [Path(row[0]) for row in cursor.fetchall()]
        return self._files_cache

    def clean(self):
        self._connection.execute("VACUUM;")
        self._connection.commit()

    def close(self):
        self._connection.close()
