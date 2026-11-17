"""Тести фільтрації та агрегації телеметрії."""

from __future__ import annotations

import types
import unittest
from datetime import datetime, timedelta, timezone

from telemetry_tool.analytics import (
    aggregate,
    critical_records,
    filter_records,
    group_by_node,
    to_sensors,
    totals,
    unique_nodes,
)
from telemetry_tool.parser import parse_text

LOG = """
TEMP-01;0x01;20.0;2026-11-17T08:00:00+02:00
TEMP-01;0x03;95.0;2026-11-17T08:05:00+02:00
PRES-01;0x01;101.0;2026-11-17T08:10:00+02:00
PRES-01;0x05;0.0;2026-11-17T08:15:00+02:00
FLOW-01;0x21;42.0;2026-11-17T08:20:00+02:00
"""


class FilterTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.records = parse_text(LOG)

    def test_filter_by_node(self) -> None:
        result = list(filter_records(self.records, nodes=["TEMP-01"]))
        self.assertEqual(len(result), 2)
        self.assertTrue(all(r.node_id == "TEMP-01" for r in result))

    def test_filter_by_value_range(self) -> None:
        result = list(filter_records(self.records, min_value=10, max_value=100))
        self.assertEqual(len(result), 3)

    def test_filter_by_sensor_type(self) -> None:
        result = list(filter_records(self.records, sensor_types=["pressure"]))
        self.assertEqual([r.node_id for r in result], ["PRES-01", "PRES-01"])

    def test_filter_by_time_window(self) -> None:
        since = datetime(2026, 11, 17, 8, 10, tzinfo=timezone(timedelta(hours=2)))
        result = list(filter_records(self.records, since=since))
        self.assertEqual(len(result), 3)

    def test_filter_critical_only(self) -> None:
        result = list(filter_records(self.records, only_critical=True))
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0].value, 95.0)

    def test_limit_and_predicate(self) -> None:
        result = list(
            filter_records(
                self.records,
                predicate=lambda r: r.value > 0,
                limit=2,
            )
        )
        self.assertEqual(len(result), 2)

    def test_filter_is_lazy(self) -> None:
        calls = 0

        def source():
            nonlocal calls
            for record in self.records:
                calls += 1
                yield record

        iterator = filter_records(source(), limit=1)
        self.assertIsInstance(iterator, types.GeneratorType)
        self.assertEqual(calls, 0)  # жодного запису до першої ітерації
        next(iterator)
        self.assertEqual(calls, 1)

    def test_grouping_and_sets(self) -> None:
        groups = group_by_node(self.records)
        self.assertEqual(
            {k: len(v) for k, v in groups.items()},
            {
                "TEMP-01": 2,
                "PRES-01": 2,
                "FLOW-01": 1,
            },
        )
        self.assertEqual(unique_nodes(self.records), {"TEMP-01", "PRES-01", "FLOW-01"})

    def test_to_sensors(self) -> None:
        sensors = list(to_sensors(self.records))
        self.assertEqual(len(sensors), 5)
        self.assertEqual(sensors[0].unit, "°C")
        self.assertEqual(sensors[1].sensor_type, "temperature")

    def test_critical_records(self) -> None:
        critical = list(critical_records(self.records))
        self.assertEqual(len(critical), 2)
        self.assertEqual([c.node_id for c in critical], ["TEMP-01", "PRES-01"])


class AggregateTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.stats = aggregate(parse_text(LOG))

    def test_per_node_statistics(self) -> None:
        temp = self.stats["TEMP-01"]
        self.assertEqual(temp.count, 2)
        self.assertEqual(temp.minimum, 20.0)
        self.assertEqual(temp.maximum, 95.0)
        self.assertAlmostEqual(temp.mean, 57.5)
        self.assertEqual(temp.critical, 1)
        self.assertEqual(temp.unit, "°C")
        self.assertEqual(temp.last_value, 95.0)

    def test_status_flags_union(self) -> None:
        self.assertIn("OVERHEAT", self.stats["TEMP-01"].flags)
        self.assertIn("LOW_BATTERY", self.stats["FLOW-01"].flags)

    def test_totals(self) -> None:
        result = totals(self.stats)
        self.assertEqual(result["nodes"], 3)
        self.assertEqual(result["records"], 5)
        self.assertEqual(result["critical"], 2)

    def test_empty_input(self) -> None:
        stats = aggregate([])
        self.assertEqual(stats, {})
        self.assertEqual(totals(stats)["records"], 0)


if __name__ == "__main__":
    unittest.main()
