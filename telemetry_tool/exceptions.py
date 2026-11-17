"""Ієрархія винятків програмного комплексу телеметрії.

Модуль не містить жодної логіки, окрім опису типів помилок, тому його
можна безпечно імпортувати з будь-якого іншого модуля пакета без ризику
циклічних залежностей.

Ієрархія::

    TelemetryError
    ├── RecordError          # пошкоджений або некоректний запис журналу
    │   ├── MalformedRecord
    │   ├── InvalidState
    │   ├── InvalidValue
    │   └── InvalidTimestamp
    └── StorageError         # проблеми з файловою системою
        ├── LogOpenError
        ├── LogReadError
        └── ReportWriteError
"""

from __future__ import annotations

__all__ = [
    "TelemetryError",
    "RecordError",
    "MalformedRecord",
    "InvalidState",
    "InvalidValue",
    "InvalidTimestamp",
    "StorageError",
    "LogOpenError",
    "LogReadError",
    "ReportWriteError",
]


class TelemetryError(Exception):
    """Базовий клас усіх винятків пакета.

    Дає змогу перехопити будь-яку помилку утиліти одним ``except`` і
    відрізнити її від сторонніх винятків інтерпретатора.
    """


class RecordError(TelemetryError):
    """Помилка окремого запису журналу.

    Attributes:
        lineno: номер рядка у вихідному файлі (1-based), якщо відомий.
        line: сирий текст рядка (може бути обрізаний для читабельності).

    """

    def __init__(self, message: str, *, lineno: int = 0, line: str = "") -> None:
        """Зберігає повідомлення та контекст пошкодженого рядка."""
        self.message = message
        self.lineno = lineno
        self.line = line
        super().__init__(message)

    def __str__(self) -> str:
        """Додає до повідомлення номер рядка, якщо він відомий."""
        prefix = f"рядок {self.lineno}: " if self.lineno else ""
        return f"{prefix}{self.message}"


class MalformedRecord(RecordError):
    """Рядок не відповідає формату журналу (невірна кількість полів тощо)."""


class InvalidState(RecordError):
    """Регістр стану не є коректним шістнадцятковим числом у діапазоні 0..0xFF."""


class InvalidValue(RecordError):
    """Виміряне значення не є скінченним числом."""


class InvalidTimestamp(RecordError):
    """Часова мітка не є коректним ISO-8601 значенням."""


class StorageError(TelemetryError):
    """Базова помилка роботи з файловою системою."""


class LogOpenError(StorageError):
    """Не вдалося відкрити вхідний журнал (немає файлу, немає прав тощо)."""


class LogReadError(StorageError):
    """Помилка читання вже відкритого журналу (обрив, кодування, I/O)."""


class ReportWriteError(StorageError):
    """Не вдалося записати підсумковий звіт."""
