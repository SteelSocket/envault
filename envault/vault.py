from pathlib import Path
from sqlcipher3 import dbapi2 as sqlite

import mimetypes


class VaultDB:
    def __init__(self, path: Path, password: str):
        self.path = path

        self._connection = sqlite.connect(path.as_posix())
        self._connection.execute(f"PRAGMA key = {password.replace("'", "''")};")
        self._connection.execute("PRAGMA foreign_keys = ON;")

        self._connection.execute("SELECT count(*) FROM sqlite_master;").fetchone()
        self.__create_tables()

        self._files_cache = None
        self._dir_cache = None

    def __ensure_root(self, path: Path) -> Path:
        if path.is_absolute():
            return path
        return Path("/") / path

    def __create_tables(self):
        self._connection.execute("""
            CREATE TABLE IF NOT EXISTS directories (
                path TEXT PRIMARY KEY
            );
        """)
        self._connection.execute("""
            CREATE TABLE IF NOT EXISTS files (
                name TEXT NOT NULL,
                dir TEXT NOT NULL,

                mime_type TEXT NOT NULL,
                data BLOB NOT NULL,

                PRIMARY KEY (name, dir),

                FOREIGN KEY (dir)
                    REFERENCES directories(path)
                    ON UPDATE CASCADE
                    ON DELETE CASCADE
            );
        """)
        self._connection.execute("""
            CREATE TABLE IF NOT EXISTS metadata (
                name TEXT NOT NULL,
                dir TEXT NOT NULL,

                key TEXT NOT NULL,
                value TEXT,

                PRIMARY KEY (name, dir, key),

                FOREIGN KEY (name, dir)
                    REFERENCES files(name, dir)
                    ON UPDATE CASCADE
                    ON DELETE CASCADE
            );
        """)
        self._connection.commit()

    def add_directory(self, path: Path):
        path = self.__ensure_root(path)

        current = Path()
        for part in path.parts:
            current /= part
            self._connection.execute(
                "INSERT OR IGNORE INTO directories(path) VALUES (?)",
                (current.as_posix(),),
            )
        self._connection.commit()
        self._dir_cache = None

    def add_file(self, path: Path, data: bytes):
        path = self.__ensure_root(path)

        self.add_directory(path.parent)

        mime_type, _ = mimetypes.guess_type(path.name)
        mime_type = mime_type or "application/octet-stream"

        self._connection.execute(
            """
            INSERT OR REPLACE INTO files(name, dir, mime_type, data)
            VALUES (?, ?, ?, ?)
            """,
            (
                path.name,
                path.parent.as_posix(),
                mime_type,
                sqlite.Binary(data),
            ),
        )

        self._connection.commit()
        self._files_cache = None

    def add_metadata(self, path: Path, key: str, value: str):
        path = self.__ensure_root(path)

        self._connection.execute(
            """
            INSERT OR REPLACE INTO metadata(name, dir, key, value)
            VALUES (?, ?, ?, ?)
            """,
            (path.name, path.parent.as_posix(), key, value),
        )
        self._connection.commit()

    def remove_directory(self, path: Path):
        path = self.__ensure_root(path)

        self._connection.execute(
            "DELETE FROM directories WHERE path = ? OR path LIKE ?",
            (path.as_posix(), path.as_posix() + "/%"),
        )

        self._connection.commit()
        self._files_cache = None
        self._dir_cache = None

    def remove_file(self, path: Path):
        self._connection.execute(
            "DELETE FROM files WHERE name = ? AND dir = ?",
            (path.name, path.parent.as_posix()),
        )

        self._connection.commit()
        self._files_cache = None

    def remove_metadata(self, path: Path, key: str):
        self._connection.execute(
            "DELETE FROM metadata WHERE name = ? AND dir = ? AND key = ?",
            (path.name, path.parent.as_posix(), key),
        )
        self._connection.commit()

    def rename_directory(self, src: Path, dst_name: str):
        src = self.__ensure_root(src)

        self._connection.execute(
            "UPDATE directories SET path = ? WHERE path = ?",
            ((src.parent / dst_name).as_posix(), src.as_posix()),
        )
        self._connection.commit()

        self._files_cache = None
        self._dir_cache = None

    def rename_file(self, src: Path, dst_name: str):
        src = self.__ensure_root(src)

        self._connection.execute(
            "UPDATE files SET name = ? WHERE name = ? AND dir = ?",
            (dst_name, src.name, src.parent.as_posix()),
        )

        self._connection.commit()
        self._files_cache = None

    def rename_metadata(self, file: Path, key: str, new_key):
        file = self.__ensure_root(file)

        self._connection.execute(
            "UPDATE metadata SET key = ? WHERE name = ? AND dir = ? AND key = ?",
            (new_key, file.name, file.parent.as_posix(), key),
        )
        self._connection.commit()

    def get_all_files(self) -> list[Path]:
        if not self._files_cache is None:
            return self._files_cache

        cursor = self._connection.execute(
            "SELECT name, dir FROM files ORDER BY dir ASC, name ASC"
        )
        self._files_cache = [Path(row[1]) / Path(row[0]) for row in cursor.fetchall()]
        return self._files_cache

    def get_files(self, dir: Path) -> list[Path]:
        dir = self.__ensure_root(dir)

        cursor = self._connection.execute(
            """
            SELECT name, dir
            FROM files
            WHERE dir = ?
            ORDER BY dir ASC, name ASC
            """,
            (dir.as_posix(),),
        )

        return [Path(row[1]) / Path(row[0]) for row in cursor.fetchall()]

    def get_all_directories(self) -> list[Path]:
        if not self._dir_cache is None:
            return self._dir_cache

        cursor = self._connection.execute("SELECT path FROM directories ORDER BY path")
        self._dir_cache = [Path(row[0]) for row in cursor.fetchall()]
        return self._dir_cache

    def get_directories(self, dir: Path) -> list[Path]:
        dir = self.__ensure_root(dir)

        cursor = self._connection.execute(
            "SELECT path FROM directories WHERE path LIKE ? ORDER BY path",
            (dir.as_posix().rstrip("/") + "/%",),
        )

        return [Path(row[0]) for row in cursor.fetchall() if Path(row[0]).parent == dir]

    def get_metadata(self, file: Path):
        file = self.__ensure_root(file)

        cursor = self._connection.execute(
            """
            SELECT key, value
            FROM metadata
            WHERE name = ? AND dir = ?
            ORDER BY key
            """,
            (
                file.name,
                file.parent.as_posix(),
            ),
        )

        return {k: v for k, v in cursor.fetchall()}

    def get_rowid_by_file(self, path: Path) -> int:
        path = self.__ensure_root(path)

        cursor = self._connection.execute(
            "SELECT rowid FROM files WHERE name = ? AND dir = ?",
            (path.name, path.parent.as_posix()),
        )

        result = cursor.fetchone()
        if result is None:
            raise FileNotFoundError()

        return result[0]

    def get_file_by_rowid(self, rowid: int) -> Path:
        cursor = self._connection.execute(
            "SELECT name, dir FROM files WHERE rowid = ?",
            (rowid,),
        )

        result = cursor.fetchone()
        if result is None:
            raise FileNotFoundError()

        return Path(result[1]) / Path(result[0])

    def read_file(self, path: Path) -> bytes:
        path = self.__ensure_root(path)

        cursor = self._connection.execute(
            "SELECT data FROM files WHERE name = ? AND dir = ?",
            (path.name, path.parent.as_posix()),
        )
        row = cursor.fetchone()

        if row is None:
            raise FileNotFoundError(path)

        return row[0]

    def write_file(self, src: Path, data: bytes):
        src = self.__ensure_root(src)
        try:
            self._connection.execute(
                "UPDATE files SET data = ? WHERE name = ? AND dir = ?",
                (data, src.name, src.parent.as_posix()),
            )
            self._connection.commit()
        except:
            pass

    def move_file(self, src: Path, dst_dir: Path):
        src = self.__ensure_root(src)
        dst_dir = self.__ensure_root(dst_dir)

        try:
            self._connection.execute(
                "UPDATE files SET dir = ? WHERE name = ? AND dir = ?",
                (dst_dir.as_posix(), src.name, src.parent.as_posix()),
            )
            self._connection.commit()
        except:
            pass

        self._files_cache = None

    def clean(self):
        self._connection.execute("VACUUM;")
        self._connection.commit()

    def close(self):
        self._connection.close()
