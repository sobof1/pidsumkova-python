"""Формування підсумкового звіту у текстовому вигляді."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from datetime import datetime

from .analytics import NodeStatistics, totals
from .exceptions import RecordError
from .models import build_sensor
from .parser import ParsedRecord
from .storage import LogSummary, ReportWriter

__all__ = ["build_report", "write_report"]

_SEPARATOR = "=" * 78
_SUBSEPARATOR = "-" * 78


def _format_table(stats: dict[str, NodeStatistics]) -> list[str]:
    """Будує вирівняну таблицю статистики по вузлах."""
    header = (
        f"{'Вузол':<10} {'Тип':<12} {'Записів':>8} {'Мін':>10} "
        f"{'Середнє':>10} {'Макс':>10} {'Од.':<6} {'Крит.':>6}  Прапорці"
    )
    lines = [header, _SUBSEPARATOR]
    for node_id in sorted(stats):
        item = stats[node_id]
        lines.append(
            f"{node_id:<10} {item.sensor_type:<12} {item.count:>8} "
            f"{item.minimum:>10.3f} {item.mean:>10.3f} {item.maximum:>10.3f} "
            f"{item.unit:<6} {item.critical:>6}  {item.status_text}"
        )
    return lines


def _format_critical(
    records: Sequence[ParsedRecord],
    *,
    limit: int = 20,
) -> list[str]:
    """Будує перелік критичних подій."""
    if not records:
        return ["Критичних подій не виявлено."]
    lines = []
    for record in records[:limit]:
        sensor = build_sensor(
            record.node_id, record.state, record.value, record.timestamp
        )
        lines.append(
            f"  {record.timestamp.isoformat()}  {record.node_id:<9} "
            f"{record.value:>9.3f} {sensor.unit:<6} 0x{record.state:02X}  "
            f"{sensor.status_text}"
        )
    hidden = len(records) - limit
    if hidden > 0:
        lines.append(f"  … ще {hidden} подій (див. повний журнал)")
    return lines


def _format_rejected(errors: Iterable[RecordError], *, limit: int = 10) -> list[str]:
    """Будує перелік відхилених рядків."""
    errors = list(errors)
    if not errors:
        return ["Пошкоджених рядків не виявлено."]
    lines = []
    for error in errors[:limit]:
        raw = error.line[:60] + ("…" if len(error.line) > 60 else "")
        lines.append(f"  {error}")
        if raw:
            lines.append(f"      ↳ {raw!r}")
    hidden = len(errors) - limit
    if hidden > 0:
        lines.append(f"  … ще {hidden} помилок")
    return lines


def build_report(
    stats: dict[str, NodeStatistics],
    summary: LogSummary | None = None,
    *,
    critical: Sequence[ParsedRecord] = (),
    rejected: Sequence[RecordError] = (),
    source: str = "—",
    generated_at: datetime | None = None,
) -> str:
    """Формує повний текстовий звіт.

    Args:
        stats: Агрегована статистика по вузлах.
        summary: Підсумок читання журналу (прийнято/відхилено).
        critical: Критичні записи для окремого розділу.
        rejected: Помилки розбору для розділу діагностики.
        source: Назва джерела даних.
        generated_at: Момент формування звіту.

    Returns:
        Готовий текст звіту (завершується символом нового рядка).

    """
    generated_at = generated_at or datetime.now().astimezone()
    aggregate_totals = totals(stats)

    lines: list[str] = [
        _SEPARATOR,
        "ЗВІТ ПРО СТАН МЕРЕЖІ МОНІТОРИНГУ".center(78).rstrip(),
        _SEPARATOR,
        f"Джерело даних : {source}",
        f"Сформовано    : {generated_at.isoformat(timespec='seconds')}",
    ]
    if summary is not None:
        lines.append(
            f"Записів       : прийнято {summary.accepted}, відхилено {summary.rejected}"
        )
    lines.extend(
        [
            f"Вузлів        : {aggregate_totals['nodes']}",
            f"Критичних     : {aggregate_totals['critical']}",
            "",
            "1. СТАТИСТИКА ЗА ВУЗЛАМИ",
            _SUBSEPARATOR,
        ]
    )
    lines.extend(_format_table(stats) if stats else ["Немає валідних записів."])

    lines.extend(["", "2. КРИТИЧНІ ПОДІЇ", _SUBSEPARATOR])
    lines.extend(_format_critical(list(critical)))

    lines.extend(["", "3. ДІАГНОСТИКА ВХІДНОГО ЖУРНАЛУ", _SUBSEPARATOR])
    lines.extend(_format_rejected(rejected))

    lines.extend(["", "4. ВИСНОВОК", _SUBSEPARATOR])
    if aggregate_totals["critical"]:
        lines.append(
            "Зафіксовано критичні прапорці стану — потрібне втручання "
            "чергового інженера."
        )
    elif stats:
        lines.append("Критичних відхилень не виявлено, мережа працює штатно.")
    else:
        lines.append("Недостатньо даних для висновку.")
    lines.append(_SEPARATOR)
    return "\n".join(lines) + "\n"


def write_report(
    path: str,
    text: str,
    *,
    encoding: str = "utf-8",
) -> None:
    """Записує звіт через менеджер контексту (атомарно)."""
    with ReportWriter(path, encoding=encoding) as writer:
        writer.write(text)
