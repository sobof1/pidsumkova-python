"""Утиліта аналізу телеметрії сенсорів комп'ютерної мережі моніторингу.

Публічний інтерфейс пакета регламентовано списком :data:`__all__`.
Імпорт підмодулів не виконується автоматично, щоб уникнути зайвих
залежностей: ``from telemetry_tool import TelemetryLog`` працює завдяки
явному реекспорту нижче.
"""

from __future__ import annotations

from .analytics import (
    NodeStatistics,
    aggregate,
    critical_records,
    filter_records,
    group_by_node,
    to_sensors,
    totals,
    unique_nodes,
)
from .exceptions import (
    InvalidState,
    InvalidTimestamp,
    InvalidValue,
    LogOpenError,
    LogReadError,
    MalformedRecord,
    RecordError,
    ReportWriteError,
    StorageError,
    TelemetryError,
)
from .models import (
    CRITICAL_FLAGS,
    FlowSensor,
    PressureSensor,
    Sensor,
    StatusFlag,
    TemperatureSensor,
    build_sensor,
    decode_status,
)
from .parser import LINE_RE, ParsedRecord, iter_records, parse_line
from .report import build_report, write_report
from .storage import LogSummary, ReportWriter, TelemetryLog

__version__ = "1.0.0"

__all__ = [
    "__version__",
    # моделі
    "Sensor",
    "TemperatureSensor",
    "PressureSensor",
    "FlowSensor",
    "StatusFlag",
    "CRITICAL_FLAGS",
    "build_sensor",
    "decode_status",
    # розбір
    "LINE_RE",
    "ParsedRecord",
    "parse_line",
    "iter_records",
    # зберігання
    "TelemetryLog",
    "ReportWriter",
    "LogSummary",
    # аналітика
    "NodeStatistics",
    "aggregate",
    "filter_records",
    "group_by_node",
    "unique_nodes",
    "critical_records",
    "to_sensors",
    "totals",
    # звіт
    "build_report",
    "write_report",
    # винятки
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
