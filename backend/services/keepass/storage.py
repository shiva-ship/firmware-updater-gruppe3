"""Geschützter Ablagebereich für hochgeladene KDBX-Dateien.

Dateien liegen unter zufälligen Namen in einem benutzerprivaten Verzeichnis außerhalb
des Repositories und außerhalb jedes ausgelieferten Webverzeichnisses.
"""

from __future__ import annotations

import logging
import os
import struct
import uuid
from collections.abc import AsyncIterator
from pathlib import Path

from backend.errors import FileTooLarge, InvalidDatabaseFile

logger = logging.getLogger(__name__)

KDBX_SIGNATURE_1 = 0x9AA2D903
KDBX_SIGNATURE_2 = 0xB54BFB67  # KeePass 2.x (KDBX); 0xB54BFB65 wäre KeePass 1.x (.kdb)
SUPPORTED_MAJOR_VERSIONS = {3, 4}
HEADER_PREFIX_LEN = 12
STORED_SUFFIX = ".kdbx"
PARTIAL_SUFFIX = ".part"


def validate_kdbx_header(prefix: bytes) -> tuple[int, int]:
    """Prüft Signatur und Version. Gibt (major, minor) zurück."""
    if len(prefix) < HEADER_PREFIX_LEN:
        raise InvalidDatabaseFile()
    sig1, sig2, minor, major = struct.unpack("<IIHH", prefix[:HEADER_PREFIX_LEN])
    if sig1 != KDBX_SIGNATURE_1 or sig2 != KDBX_SIGNATURE_2:
        raise InvalidDatabaseFile()
    if major not in SUPPORTED_MAJOR_VERSIONS:
        raise InvalidDatabaseFile("Nicht unterstützte KDBX-Version. Unterstützt werden KDBX 3.1 und KDBX 4.x.")
    return major, minor


def sanitize_display_name(name: str) -> str:
    """Nur für die Anzeige – der Dateiname wird nie als Pfad verwendet."""
    base = name.replace("\\", "/").rsplit("/", 1)[-1]
    cleaned = "".join(ch for ch in base if ch.isprintable() and ch not in '<>:"|?*')
    cleaned = cleaned.strip().strip(".") or "datenbank.kdbx"
    return cleaned[:128]


class UploadStorage:
    def __init__(self, directory: Path) -> None:
        self.directory = directory

    def prepare(self) -> None:
        self.directory.mkdir(parents=True, exist_ok=True)
        try:
            os.chmod(self.directory, 0o700)  # unter Windows wirkungslos; dort schützt %LOCALAPPDATA%
        except OSError:
            pass

    def wipe(self) -> int:
        """Entfernt verwaiste Dateien (z. B. nach einem Absturz). Nur eigene Dateimuster."""
        removed = 0
        if not self.directory.exists():
            return 0
        for path in self.directory.iterdir():
            if path.is_file() and path.suffix in (STORED_SUFFIX, PARTIAL_SUFFIX):
                self.delete(path)
                removed += 1
        return removed

    async def save_stream(self, chunks: AsyncIterator[bytes], max_bytes: int) -> tuple[Path, int]:
        """Schreibt den Upload in eine neue Datei, validiert Header und Größe."""
        self.prepare()
        file_id = uuid.uuid4().hex
        partial = self.directory / f"{file_id}{PARTIAL_SUFFIX}"
        final = self.directory / f"{file_id}{STORED_SUFFIX}"
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0)
        fd = os.open(partial, flags, 0o600)
        size = 0
        prefix = b""
        validated = False
        try:
            with os.fdopen(fd, "wb") as fh:
                async for chunk in chunks:
                    if not chunk:
                        continue
                    size += len(chunk)
                    if size > max_bytes:
                        raise FileTooLarge()
                    if not validated:
                        prefix += chunk[: HEADER_PREFIX_LEN - len(prefix)]
                        if len(prefix) >= HEADER_PREFIX_LEN:
                            validate_kdbx_header(prefix)
                            validated = True
                    fh.write(chunk)
            if not validated:
                raise InvalidDatabaseFile()
            os.replace(partial, final)
        except BaseException:
            self.delete(partial)
            raise
        return final, size

    def delete(self, path: Path) -> None:
        try:
            path.unlink(missing_ok=True)
        except OSError:
            logger.warning("Temporäre Datei konnte nicht gelöscht werden: %s", path.name)
