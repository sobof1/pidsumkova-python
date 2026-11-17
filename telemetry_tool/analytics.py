"""Фільтрація та агрегація телеметрії.

Усі функції фільтрації є генераторами: вони не створюють проміжних
списків, тому пам'ять споживається пропорційно до одного запису, а не
до розміру журналу.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass, field
from datetime import datetime

from .models import CRITICAL_FLAGS, Sensor, build_sensor, decode_status
from .parser import ParsedRecord

__all__ = [
    "NodeStatistics",
    "filter_records",
    "to_sensors",
    "group_by_node",
    "unique_nodes",
    "critical_records",
    "aggregate",
    "totals",
]


@dataclass
class NodeStatistics:
    """Накопичувальна статистика одного вузла.

    Об'єкт змінний і призначений для одного проходу агрегації.
    """

    node_id: str
    sensor_type: str = "generic"
    unit: str = ""
    count: int = 0
    critical: int = 0
    total: float = 0.0
    minimum: float = float("inf")
    maximum: float = float("-inf")
    last_value: float = 0.0
    last_timestamp: datetime | None = None
    flags: set[str] = field(default_factory=set)

    def add(self, record: ParsedRecord) -> None:
        """Додає одне показання до статистики."""
        sensor = build_sensor(
            record.node_id, record.state, record.value, record.timestamp
        )
        self.node_id = record.node_id
        self.sensor_type = sensor.sensor_type
        self.unit = sensor.unit
        self.count += 1
        self.total += record.value
        self.minimum = min(self.minimum, record.value)
        self.maximum = max(self.maximum, record.value)
        if record.state & int(CRITICAL_FLAGS):
            self.critical += 1
        self.flags.update(decode_status(record.state))
        if self.last_timestamp is None or record.timestamp >= self.last_timestamp:
            self.last_timestamp = record.timestamp
            self.last_value = record.value

    @property
    def mean(self) -> float:
        """Середнє арифметичне (0.0 для порожньої статистики)."""
        return self.total / self.count if self.count else 0.0

    @property
    def span(self) -> float:
        """Розмах: максимум мінус мінімум."""
        return self.maximum - self.minimum if self.count else 0.0

    @property
    def status_text(self) -> str:
        """Усі прапорці, що зустрічалися на вузлі."""
        return "|".join(sorted(self.flags)) or "OK"


def filter_records(
    records: Iterable[ParsedRecord],
    *,
    nodes: Iterable[str] | None = None,
    sensor_types: Iterable[str] | None = None,
    min_value: float | None = None,
    max_value: float | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
    only_critical: bool = False,
    predicate: Callable[[ParsedRecord], bool] | None = None,
    limit: int | None = None,
) -> Iterator[ParsedRecord]:
    """Фільтрує записи журналу за набором незалежних критеріїв.

    Усі параметри — keyword-only, що унеможливлює випадкову плутанину
    порядку аргументів. Функція повертає генератор.

    Args:
        records: Джерело записів (файл, генератор, список).
        nodes: Дозволені ідентифікатори вузлів (перевірка за множиною).
        sensor_types: Дозволені типи сенсорів (``temperature`` тощо).
        min_value: Нижня межа значення включно.
        max_value: Верхня межа значення включно.
        since: Початковий момент часу включно.
        until: Кінцевий момент часу включно.
        only_critical: Лишати лише записи з критичними прапорцями.
        predicate: Довільний додатковий предикат.
        limit: Максимальна кількість результатів.

    Yields:
        Записи, що задовольняють усі задані умови.

    """
    node_set = set(nodes) if nodes is not None else None
    type_set = set(sensor_types) if sensor_types is not None else None
    emitted = 0

    for record in records:
        if node_set is not None and record.node_id not in node_set:
            continue
        if min_value is not None and record.value < min_value:
            continue
        if max_value is not None and record.value > max_value:
            continue
        if since is not None and record.timestamp < since:
            continue
        if until is not None and record.timestamp > until:
            continue
        if only_critical or type_set is not None:
            sensor = build_sensor(
                record.node_id, record.state, record.value, record.timestamp
            )
            if only_critical and not sensor.is_critical:
                continue
            if type_set is not None and sensor.sensor_type not in type_set:
                continue
        if predicate is not None and not predicate(record):
            continue
        yield record
        emitted += 1
        if limit is not None and emitted >= limit:
            return


def to_sensors(records: Iterable[ParsedRecord]) -> Iterator[Sensor]:
    """Перетворює записи у відповідні об'єкти сенсорів (ліниво)."""
    for record in records:
        yield build_sensor(record.node_id, record.state, record.value, record.timestamp)


def group_by_node(
    records: Iterable[ParsedRecord],
) -> dict[str, list[ParsedRecord]]:
    """Групує записи за унікальними вузлами.

    Повертає словник ``{node_id: [records]}``. Словник збережено як
    ``dict`` (амортизовано O(1) на вставку) замість списку пар, бо
    пошук за вузлом — основна операція звіту.
    """
    groups: dict[str, list[ParsedRecord]] = {}
    for record in records:
        groups.setdefault(record.node_id, []).append(record)
    return groups


def unique_nodes(records: Iterable[ParsedRecord]) -> set[str]:
    """Повертає множину унікальних ідентифікаторів вузлів."""
    return {record.node_id for record in records}


def critical_records(records: Iterable[ParsedRecord]) -> Iterator[ParsedRecord]:
    """Генератор лише критичних записів."""
    for record in records:
        sensor = build_sensor(
            record.node_id, record.state, record.value, record.timestamp
        )
        if sensor.is_critical:
            yield record


def aggregate(records: Iterable[ParsedRecord]) -> dict[str, NodeStatistics]:
    """Обчислює статистику по кожному вузлу за один прохід.

    Returns:
        Словник ``{node_id: NodeStatistics}`` у порядку першої появи.

    """
    stats: dict[str, NodeStatistics] = {}
    for record in records:
        bucket = stats.get(record.node_id)
        if bucket is None:
            bucket = NodeStatistics(node_id=record.node_id)
            stats[record.node_id] = bucket
        bucket.add(record)
    return stats


def totals(stats: dict[str, NodeStatistics]) -> dict[str, float | int]:
    """Згортає статистику по вузлах у загальні підсумки."""
    count = sum(item.count for item in stats.values())
    critical = sum(item.critical for item in stats.values())
    total = sum(item.total for item in stats.values())
    return {
        "nodes": len(stats),
        "records": count,
        "critical": critical,
        "mean": total / count if count else 0.0,
    }
