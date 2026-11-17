"""Тести об'єктної моделі сенсорів."""

from __future__ import annotations

import unittest
from datetime import UTC, datetime

from telemetry_tool.exceptions import InvalidState, InvalidValue
from telemetry_tool.models import (
    CRITICAL_FLAGS,
    FlowSensor,
    PressureSensor,
    Sensor,
    StatusFlag,
    TemperatureSensor,
    build_sensor,
    decode_status,
)

MOMENT = datetime(2026, 11, 17, 8, 0, tzinfo=UTC)


class StatusFlagTestCase(unittest.TestCase):
    def test_decode_status(self) -> None:
        self.assertEqual(decode_status(0x0B), ("ONLINE", "OVERHEAT", "SENSOR_FAULT"))
        self.assertEqual(decode_status(0x00), ())
        with self.assertRaises(InvalidState):
            decode_status(0x100)

    def test_bitwise_critical_detection(self) -> None:
        self.assertTrue(0x03 & int(CRITICAL_FLAGS))
        self.assertFalse(0x21 & int(CRITICAL_FLAGS))


class SensorTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.sensor = TemperatureSensor("TEMP-01", 0x0F, 23.54, MOMENT)

    def test_properties_are_read_only(self) -> None:
        with self.assertRaises(AttributeError):
            self.sensor.value = 100.0  # type: ignore[misc]

    def test_flags_and_critical(self) -> None:
        self.assertTrue(self.sensor.has_flag(StatusFlag.OVERHEAT))
        self.assertTrue(self.sensor.has_flag(StatusFlag.OVERHEAT | StatusFlag.ONLINE))
        self.assertFalse(self.sensor.has_flag(StatusFlag.MAINTENANCE))
        self.assertTrue(self.sensor.is_critical)
        self.assertEqual(
            self.sensor.status_text, "ONLINE|OVERHEAT|POWER_FAIL|SENSOR_FAULT"
        )
        self.assertEqual(self.sensor.with_flag(StatusFlag.MAINTENANCE), 0x8F)

    def test_in_range(self) -> None:
        self.assertTrue(self.sensor.in_range)
        hot = TemperatureSensor("TEMP-01", 0x01, 130.0, MOMENT)
        self.assertFalse(hot.in_range)

    def test_dunder_methods(self) -> None:
        same = TemperatureSensor("TEMP-01", 0x0F, 23.54, MOMENT)
        other = PressureSensor("TEMP-01", 0x0F, 23.54, MOMENT)
        self.assertEqual(self.sensor, same)
        self.assertEqual(self.sensor, other)  # порівняння за полями
        self.assertEqual(hash(self.sensor), hash(same))
        self.assertNotEqual(self.sensor, "TEMP-01")
        self.assertIn("TEMP-01", str(self.sensor))
        self.assertIn("°C", str(self.sensor))
        self.assertIn("TemperatureSensor(node_id='TEMP-01'", repr(self.sensor))
        self.assertIn("0x0F", repr(self.sensor))

    def test_ordering(self) -> None:
        later = TemperatureSensor("TEMP-02", 0x01, 20.0, MOMENT)
        self.assertLess(self.sensor, later)

    def test_validation(self) -> None:
        with self.assertRaises(InvalidState):
            TemperatureSensor("", 0x01, 1.0, MOMENT)
        with self.assertRaises(InvalidState):
            TemperatureSensor("TEMP-01", 0x100, 1.0, MOMENT)
        with self.assertRaises(InvalidState):
            TemperatureSensor("TEMP-01", True, 1.0, MOMENT)
        with self.assertRaises(InvalidValue):
            TemperatureSensor("TEMP-01", 0x01, float("inf"), MOMENT)
        with self.assertRaises(TypeError):
            Sensor("TEMP-01", 0x01, 1.0, "2026-11-17")  # type: ignore[arg-type]

    def test_serialisation_round_trip(self) -> None:
        self.assertEqual(self.sensor.as_tuple()[0], "TEMP-01")
        self.assertIn("TEMP-01;0x0F;23.540;", self.sensor.to_log_line())


class FactoryTestCase(unittest.TestCase):
    def test_resolves_specialised_classes(self) -> None:
        sensor = build_sensor("TEMP-09", 1, 1.0, MOMENT)
        self.assertIsInstance(sensor, TemperatureSensor)
        sensor = build_sensor("PRES-09", 1, 1.0, MOMENT)
        self.assertIsInstance(sensor, PressureSensor)
        sensor = build_sensor("FLOW-09", 1, 1.0, MOMENT)
        self.assertIsInstance(sensor, FlowSensor)
        self.assertIs(type(build_sensor("PUMP-09", 1, 1.0, MOMENT)), Sensor)

    def test_subclass_units(self) -> None:
        self.assertEqual(build_sensor("TEMP-09", 1, 1.0, MOMENT).unit, "°C")
        self.assertEqual(build_sensor("PRES-09", 1, 1.0, MOMENT).unit, "kPa")
        self.assertEqual(build_sensor("FLOW-09", 1, 1.0, MOMENT).unit, "L/min")


if __name__ == "__main__":
    unittest.main()
