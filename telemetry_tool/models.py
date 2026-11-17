"""Об'єктна модель телеметричних даних.

Модуль описує:

* :class:`StatusFlag` — 8-бітний регістр стану апаратного сенсора;
* :class:`Sensor` — базовий клас сенсора з інкапсуляцією через
  :func:`property` та перевантаженими dunder-методами;
* спеціалізовані класи :class:`TemperatureSensor`, :class:`PressureSensor`,
  :class:`FlowSensor` з власними одиницями вимірювання та межами;
* фабрику :func:`build_sensor`, яка за ідентифікатором вузла обирає
  конкретний клас.
"""

from __future__ import annotations

import math
from datetime import datetime
from enum import IntFlag
from typing import ClassVar, Final

from .exceptions import InvalidState, InvalidValue

__all__ = [
    "StatusFlag",
    "CRITICAL_FLAGS",
    "decode_status",
    "Sensor",
    "TemperatureSensor",
    "PressureSensor",
    "FlowSensor",
    "SENSOR_TYPES",
    "resolve_sensor_type",
    "build_sensor",
]


class StatusFlag(IntFlag):
    """Прапорці регістру стану (молодший байт).

    Кожен прапорець займає рівно один біт, тому перевірка виконується
    побітовим ``AND``: ``state & StatusFlag.OVERHEAT``.
    """

    NONE = 0x00
    ONLINE = 0x01
    OVERHEAT = 0x02
    POWER_FAIL = 0x04
    SENSOR_FAULT = 0x08
    CALIBRATION = 0x10
    LOW_BATTERY = 0x20
    COMM_ERROR = 0x40
    MAINTENANCE = 0x80


#: Прапорці, будь-який з яких робить показання критичним.
CRITICAL_FLAGS: Final[StatusFlag] = (
    StatusFlag.OVERHEAT
    | StatusFlag.POWER_FAIL
    | StatusFlag.SENSOR_FAULT
    | StatusFlag.COMM_ERROR
)


def decode_status(state: int) -> tuple[str, ...]:
    """Розшифровує бітову маску у кортеж назв встановлених прапорців.

    Args:
        state: Значення регістру стану (0..0xFF).

    Returns:
        Кортеж імен прапорців у порядку зростання бітів.

    Raises:
        InvalidState: Якщо значення виходить за межі байта.

    """
    if not 0 <= state <= 0xFF:
        raise InvalidState(f"регістр стану поза діапазоном 0..0xFF: {state!r}")
    return tuple(flag.name for flag in StatusFlag if flag.value and state & flag.value)


class Sensor:
    """Базовий клас одного показання сенсора.

    Об'єкт є незмінним: усі поля доступні лише через read-only
    властивості, а конфігурація задається в конструкторі. Це дозволяє
    безпечно використовувати показання як ключі словників і елементи
    множин.

    Attributes:
        sensor_type: Тип сенсора (перевизначається у нащадках).
        unit: Одиниця вимірювання (перевизначається у нащадках).
        normal_range: Допустимий діапазон значень.

    """

    __slots__ = ("_node_id", "_state", "_value", "_timestamp")

    sensor_type: ClassVar[str] = "generic"
    unit: ClassVar[str] = ""
    normal_range: ClassVar[tuple[float, float]] = (-math.inf, math.inf)

    def __init__(
        self,
        node_id: str,
        state: int,
        value: float,
        timestamp: datetime,
    ) -> None:
        """Створює показання сенсора після перевірки інваріантів.

        Args:
            node_id: Ідентифікатор мережевого вузла, наприклад ``TEMP-01``.
            state: Байт прапорців стану.
            value: Виміряне значення (скінченне число).
            timestamp: Часова мітка вимірювання.

        Raises:
            InvalidState: Некоректний ідентифікатор або регістр стану.
            InvalidValue: Значення не є скінченним числом.
            TypeError: Якщо ``timestamp`` не є :class:`datetime`.

        """
        if not isinstance(node_id, str) or not node_id.strip():
            raise InvalidState("порожній ідентифікатор вузла")
        if isinstance(state, bool) or not isinstance(state, int):
            raise InvalidState(
                f"регістр стану має бути int, отримано {type(state).__name__}"
            )
        if not 0 <= state <= 0xFF:
            raise InvalidState(f"регістр стану поза діапазоном 0..0xFF: {state!r}")
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise InvalidValue(
                f"значення має бути числом, отримано {type(value).__name__}"
            )
        value = float(value)
        if not math.isfinite(value):
            raise InvalidValue(f"значення не є скінченним: {value!r}")
        if not isinstance(timestamp, datetime):
            raise TypeError("timestamp має бути datetime")

        self._node_id = node_id
        self._state = state
        self._value = value
        self._timestamp = timestamp

    # ------------------------------------------------------------------
    # Публічні властивості (інкапсуляція через @property)
    # ------------------------------------------------------------------
    @property
    def node_id(self) -> str:
        """Ідентифікатор вузла."""
        return self._node_id

    @property
    def state(self) -> int:
        """Сира бітова маска стану."""
        return self._state

    @property
    def value(self) -> float:
        """Виміряне значення."""
        return self._value

    @property
    def timestamp(self) -> datetime:
        """Часова мітка вимірювання."""
        return self._timestamp

    @property
    def flags(self) -> StatusFlag:
        """Маска стану, типізована як :class:`StatusFlag`."""
        return StatusFlag(self._state)

    @property
    def status_names(self) -> tuple[str, ...]:
        """Назви встановлених прапорців."""
        return decode_status(self._state)

    @property
    def status_text(self) -> str:
        """Людиночитний рядок прапорців (``OK`` для нульової маски)."""
        return "|".join(self.status_names) or "OK"

    @property
    def is_critical(self) -> bool:
        """``True``, якщо встановлено хоча б один критичний прапорець."""
        return bool(self._state & int(CRITICAL_FLAGS))

    @property
    def in_range(self) -> bool:
        """``True``, якщо значення лежить у межах ``normal_range``."""
        low, high = self.normal_range
        return low <= self._value <= high

    # ------------------------------------------------------------------
    # Побітові операції
    # ------------------------------------------------------------------
    def has_flag(self, flag: StatusFlag) -> bool:
        """Перевіряє, чи встановлено конкретний прапорець.

        Args:
            flag: Прапорець або їх комбінація.

        Returns:
            ``True``, якщо всі біти ``flag`` присутні у стані.

        """
        mask = int(flag)
        return mask != 0 and (self._state & mask) == mask

    def with_flag(self, flag: StatusFlag) -> int:
        """Повертає нову маску стану з увімкненим прапорцем."""
        return self._state | int(flag)

    # ------------------------------------------------------------------
    # Dunder-методи
    # ------------------------------------------------------------------
    def __str__(self) -> str:
        """Компактне представлення для звіту."""
        return (
            f"{self._node_id} = {self._value:.3f}{self.unit} "
            f"[0x{self._state:02X}: {self.status_text}] "
            f"@ {self._timestamp.isoformat()}"
        )

    def __repr__(self) -> str:
        """Представлення, придатне для відтворення об'єкта."""
        return (
            f"{type(self).__name__}("
            f"node_id={self._node_id!r}, "
            f"state=0x{self._state:02X}, "
            f"value={self._value!r}, "
            f"timestamp={self._timestamp.isoformat()!r})"
        )

    def __eq__(self, other: object) -> bool:
        """Порівнює показання за всіма чотирма полями.

        Клас нащадка не враховується: ``TEMP-01`` з тими самими даними
        дорівнює будь-якому іншому :class:`Sensor` з такими полями.
        """
        if not isinstance(other, Sensor):
            return NotImplemented
        return (
            self._node_id == other._node_id
            and self._state == other._state
            and self._value == other._value
            and self._timestamp == other._timestamp
        )

    def __hash__(self) -> int:
        """Хеш узгоджений з :meth:`__eq__`."""
        return hash((self._node_id, self._state, self._value, self._timestamp))

    def __lt__(self, other: Sensor) -> bool:
        """Сортування за часом, потім за вузлом."""
        if not isinstance(other, Sensor):
            return NotImplemented
        return (self._timestamp, self._node_id) < (other._timestamp, other._node_id)

    # ------------------------------------------------------------------
    # Серіалізація
    # ------------------------------------------------------------------
    def as_tuple(self) -> tuple[str, int, float, datetime]:
        """Повертає дані як кортеж (незмінна структура для агрегації)."""
        return (self._node_id, self._state, self._value, self._timestamp)

    def to_log_line(self) -> str:
        """Серіалізує показання назад у формат журналу."""
        return (
            f"{self._node_id};0x{self._state:02X};"
            f"{self._value:.3f};{self._timestamp.isoformat()}"
        )


class TemperatureSensor(Sensor):
    """Сенсор температури, °C."""

    sensor_type = "temperature"
    unit = "°C"
    normal_range = (-40.0, 125.0)


class PressureSensor(Sensor):
    """Сенсор тиску, кПа."""

    sensor_type = "pressure"
    unit = "kPa"
    normal_range = (0.0, 1000.0)


class FlowSensor(Sensor):
    """Сенсор витрати, л/хв."""

    sensor_type = "flow"
    unit = "L/min"
    normal_range = (0.0, 500.0)


#: Відображення префікса вузла на конкретний клас сенсора.
SENSOR_TYPES: Final[dict[str, type[Sensor]]] = {
    "TEMP": TemperatureSensor,
    "PRES": PressureSensor,
    "FLOW": FlowSensor,
}


def resolve_sensor_type(node_id: str) -> type[Sensor]:
    """Визначає клас сенсора за префіксом ідентифікатора вузла.

    Args:
        node_id: Ідентифікатор вузла, наприклад ``TEMP-01``.

    Returns:
        Відповідний клас сенсора або :class:`Sensor`, якщо префікс
        невідомий (розширюваність без зміни парсера).

    """
    prefix = node_id.split("-", 1)[0].upper()
    return SENSOR_TYPES.get(prefix, Sensor)


def build_sensor(
    node_id: str,
    state: int,
    value: float,
    timestamp: datetime,
) -> Sensor:
    """Фабрична функція: створює сенсор потрібного підкласу."""
    return resolve_sensor_type(node_id)(node_id, state, value, timestamp)
