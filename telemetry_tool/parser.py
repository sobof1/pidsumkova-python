"""Синтаксичний розбір рядків журналу телеметрії.

Формат рядка (поля розділені крапкою з комою)::

    NODE-ID ; STATE ; VALUE ; TIMESTAMP
    TEMP-01 ; 0x0F  ; 23.54 ; 2026-11-17T08:00:00+02:00

Регулярний вираз :data:`LINE_RE` описаний у режимі ``re.VERBOSE`` і
використовує іменовані групи, що одночасно виконує роль валідатора та
екстрактора полів.
"""

from __future__ import annotations

import math
import re
from collections.abc import Iterable, Iterator
from datetime import datetime
from typing import NamedTuple

from .exceptions import (
    InvalidState,
    InvalidTimestamp,
    InvalidValue,
    MalformedRecord,
    RecordError,
)

__all__ = [
    "LINE_RE",
    "ParsedRecord",
    "parse_line",
    "parse_state",
    "parse_value",
    "parse_timestamp",
    "iter_records",
    "parse_text",
]


#: Шаблон одного запису. Кожна група — одне поле майбутнього кортежу.
LINE_RE = re.compile(
    r"""
    ^\s*
    (?P<node>[A-Z]{2,8}-[0-9]{1,4})                  # ідентифікатор вузла
    \s*;\s*
    (?P<state>(?:0[xX])?[0-9A-Fa-f]{2})              # байт стану у hex
    \s*;\s*
    (?P<value>[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?)  # число
    \s*;\s*
    (?P<timestamp>
        \d{4}-\d{2}-\d{2}
        [T ]
        \d{2}:\d{2}:\d{2}
        (?:\.\d{1,6})?
        (?:Z|[+-]\d{2}:\d{2})?
    )
    \s*$
    """,
    re.VERBOSE,
)


class ParsedRecord(NamedTuple):
    """Результат розбору одного рядка.

    ``NamedTuple`` обрано тому, що це незмінна структура з фіксованим
    набором полів: вона компактна, хешована і розпаковується як кортеж.

    Attributes:
        node_id: Ідентифікатор вузла.
        state: Байт стану (0..0xFF).
        value: Виміряне значення.
        timestamp: Часова мітка.
        lineno: Номер рядка у файлі (для діагностики).

    """

    node_id: str
    state: int
    value: float
    timestamp: datetime
    lineno: int


def parse_state(text: str) -> int:
    """Перетворює шістнадцятковий текст у байт стану.

    Args:
        text: Рядок вигляду ``0x0F`` або ``0F``.

    Returns:
        Ціле число 0..0xFF.

    Raises:
        InvalidState: Якщо текст не є hex-байтом.

    """
    cleaned = text.strip()
    if cleaned[:2].lower() == "0x":
        cleaned = cleaned[2:]
    try:
        state = int(cleaned, 16)
    except ValueError as exc:
        raise InvalidState(f"некоректний hex-регістр стану: {text!r}") from exc
    if not 0 <= state <= 0xFF:
        raise InvalidState(f"регістр стану поза межами байта: {text!r}")
    return state


def parse_value(text: str) -> float:
    """Перетворює текст у скінченне число з рухомою комою.

    Raises:
        InvalidValue: Якщо число некоректне або не скінченне.

    """
    try:
        value = float(text)
    except ValueError as exc:
        raise InvalidValue(f"некоректне числове значення: {text!r}") from exc
    if not math.isfinite(value):
        raise InvalidValue(f"значення не є скінченним: {text!r}")
    return value


def parse_timestamp(text: str) -> datetime:
    """Розбирає ISO-8601 мітку часу (з ``Z`` або зсувом).

    Raises:
        InvalidTimestamp: Якщо рядок не є коректною датою/часом.

    """
    normalized = text.strip()
    if normalized.endswith(("Z", "z")):
        normalized = normalized[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise InvalidTimestamp(f"некоректна часова мітка: {text!r}") from exc


def parse_line(raw: str, lineno: int = 0) -> ParsedRecord:
    """Розбирає один рядок журналу у :class:`ParsedRecord`.

    Args:
        raw: Сирий рядок (може містити пробіли та символи нового рядка).
        lineno: Номер рядка для повідомлень про помилки.

    Returns:
        Заповнений :class:`ParsedRecord`.

    Raises:
        MalformedRecord: Рядок не відповідає шаблону.
        InvalidState: Hex-поле стану некоректне.
        InvalidValue: Числове поле некоректне.
        InvalidTimestamp: Часова мітка некоректна.

    """
    match = LINE_RE.match(raw)
    if match is None:
        raise MalformedRecord(
            "рядок не відповідає формату NODE;STATE;VALUE;TIMESTAMP",
            lineno=lineno,
            line=raw.rstrip("\n"),
        )

    fields = match.groupdict()
    try:
        return ParsedRecord(
            node_id=fields["node"],
            state=parse_state(fields["state"]),
            value=parse_value(fields["value"]),
            timestamp=parse_timestamp(fields["timestamp"]),
            lineno=lineno,
        )
    except RecordError as exc:
        # Доповнюємо помилку контекстом рядка, не втрачаючи тип.
        exc.lineno = lineno
        exc.line = raw.rstrip("\n")
        raise


def iter_records(
    stream: Iterable[str],
    *,
    errors: list[RecordError] | None = None,
    strict: bool = False,
    skip_blank: bool = True,
    skip_comments: bool = True,
) -> Iterator[ParsedRecord]:
    """Ліниво читає журнал і повертає валідні записи.

    Функція є генератором: файл не завантажується в пам'ять повністю,
    а обробляється рядок за рядком.

    Args:
        stream: Будь-який ітерабельний об'єкт рядків (файл, список).
        errors: Якщо задано, сюди додаються пошкоджені записи.
        strict: Якщо ``True``, перша ж помилка перериває читання.
        skip_blank: Ігнорувати порожні рядки.
        skip_comments: Ігнорувати рядки, що починаються з ``#``.

    Yields:
        :class:`ParsedRecord` для кожного валідного рядка.

    Raises:
        RecordError: У режимі ``strict`` — перша знайдена помилка.

    """
    for lineno, raw in enumerate(stream, start=1):
        stripped = raw.strip()
        if skip_blank and not stripped:
            continue
        if skip_comments and stripped.startswith("#"):
            continue
        try:
            yield parse_line(raw, lineno)
        except RecordError as exc:
            if strict:
                raise
            if errors is not None:
                errors.append(exc)


def parse_text(text: str, *, strict: bool = False) -> list[ParsedRecord]:
    """Зручний хелпер для розбору рядка/тексту в пам'яті (тести, REPL)."""
    return list(iter_records(text.splitlines(), strict=strict))
