"""Командний інтерфейс утиліти телеметрії.

Запуск::

    python -m telemetry_tool data/telemetry.log -o report.txt
    python -m telemetry_tool data/telemetry.log --node TEMP-01 --critical-only
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Iterator, Sequence
from datetime import datetime
from pathlib import Path

from .analytics import NodeStatistics, aggregate, filter_records
from .exceptions import LogOpenError, LogReadError, RecordError, ReportWriteError
from .models import CRITICAL_FLAGS, SENSOR_TYPES
from .parser import ParsedRecord
from .report import build_report
from .storage import ReportWriter, TelemetryLog

__all__ = ["main", "build_parser"]


def _iso_datetime(text: str) -> datetime:
    """Тип аргументу командного рядка: ISO-8601 дата/час."""
    normalized = text.strip()
    if normalized.endswith(("Z", "z")):
        normalized = normalized[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            f"очікується ISO-8601, отримано {text!r}"
        ) from exc


def _tap(
    records: Iterator[ParsedRecord],
    sink: list[ParsedRecord],
) -> Iterator[ParsedRecord]:
    """Пропускає записи далі, попутно збираючи критичні у ``sink``."""
    for record in records:
        if record.state & int(CRITICAL_FLAGS):
            sink.append(record)
        yield record


def build_parser() -> argparse.ArgumentParser:
    """Створює парсер аргументів командного рядка."""
    parser = argparse.ArgumentParser(
        prog="telemetry_tool",
        description="Аналіз журналу телеметрії сенсорів мережі моніторингу.",
    )
    parser.add_argument("log", type=Path, help="шлях до вхідного журналу")
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=None,
        help="шлях до звіту (типово: <журнал>.report.txt)",
    )
    parser.add_argument(
        "--node",
        action="append",
        dest="nodes",
        metavar="ID",
        help="враховувати лише вказаний вузол (можна повторювати)",
    )
    parser.add_argument(
        "--sensor-type",
        action="append",
        dest="sensor_types",
        choices=sorted(
            {"generic", *(cls.sensor_type for cls in SENSOR_TYPES.values())}
        ),
        help="враховувати лише вказаний тип сенсора",
    )
    parser.add_argument("--min-value", type=float, help="нижня межа значення")
    parser.add_argument("--max-value", type=float, help="верхня межа значення")
    parser.add_argument("--since", type=_iso_datetime, help="початок інтервалу (ISO)")
    parser.add_argument("--until", type=_iso_datetime, help="кінець інтервалу (ISO)")
    parser.add_argument(
        "--critical-only",
        action="store_true",
        help="лишити лише записи з критичними прапорцями",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="зупинятися на першому пошкодженому рядку",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="не друкувати підсумок у stdout",
    )
    return parser


def run(args: argparse.Namespace) -> int:
    """Виконує один сеанс обробки; повертає код виходу."""
    output = args.output or args.log.with_name(args.log.name + ".report.txt")
    log = TelemetryLog(args.log, strict=args.strict)
    exit_code = 0

    try:
        try:
            with log:
                critical: list[ParsedRecord] = []
                stats: dict[str, NodeStatistics] = aggregate(
                    _tap(
                        filter_records(
                            log,
                            nodes=args.nodes,
                            sensor_types=args.sensor_types,
                            min_value=args.min_value,
                            max_value=args.max_value,
                            since=args.since,
                            until=args.until,
                            only_critical=args.critical_only,
                        ),
                        critical,
                    )
                )
        except LogOpenError as exc:
            print(f"Помилка доступу до журналу: {exc}", file=sys.stderr)
            exit_code = 2
        except LogReadError as exc:
            print(f"Помилка читання журналу: {exc}", file=sys.stderr)
            exit_code = 2
        except RecordError as exc:
            print(f"Пошкоджений запис (strict): {exc}", file=sys.stderr)
            exit_code = 2
        else:
            try:
                report_text = build_report(
                    stats,
                    log.summary(),
                    critical=critical,
                    rejected=log.errors,
                    source=str(args.log),
                )
                with ReportWriter(output) as writer:
                    writer.write(report_text)
            except ReportWriteError as exc:
                print(f"Помилка запису звіту: {exc}", file=sys.stderr)
                exit_code = 3
            else:
                if not args.quiet:
                    print(f"Звіт збережено: {output}")
                    print(
                        f"Вузлів: {len(stats)}, записів: {log.read_count}, "
                        f"критичних: {len(critical)}, "
                        f"відхилено: {len(log.errors)}"
                    )
            finally:
                # Діагностика виконується незалежно від успіху запису.
                if not args.quiet:
                    for error in log.errors[:5]:
                        print(f"  ! {error}", file=sys.stderr)
    finally:
        if log.errors and not args.quiet:
            print(
                f"Увага: пропущено пошкоджених рядків — {len(log.errors)}",
                file=sys.stderr,
            )

    return exit_code


def main(argv: Sequence[str] | None = None) -> int:
    """Точка входу CLI. Повертає код виходу процесу."""
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return run(args)
    except KeyboardInterrupt:
        print("Перервано користувачем", file=sys.stderr)
        return 130
    except Exception as exc:  # noqa: BLE001 - останній рубіж захисту CLI
        print(f"Непередбачена помилка: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
