"""Тести розбору журналу та регулярного виразу."""

from __future__ import annotations

import unittest
from datetime import UTC, datetime, timedelta, timezone

from telemetry_tool.exceptions import (
    InvalidState,
    InvalidValue,
    MalformedRecord,
    RecordError,
)
from telemetry_tool.parser import (
    LINE_RE,
    ParsedRecord,
    iter_records,
    parse_line,
    parse_state,
    parse_timestamp,
    parse_value,
)

GOOD_LINE = "TEMP-01;0x0F;23.54;2026-11-17T08:00:00+02:00"


class ParserTestCase(unittest.TestCase):
    def test_regex_extracts_named_groups(self) -> None:
        match = LINE_RE.match(GOOD_LINE)
        self.assertIsNotNone(match)
        assert match is not None
        self.assertEqual(match.group("node"), "TEMP-01")
        self.assertEqual(match.group("state"), "0x0F")
        self.assertEqual(match.group("value"), "23.54")
        self.assertEqual(match.group("timestamp"), "2026-11-17T08:00:00+02:00")

    def test_parse_line_returns_named_tuple(self) -> None:
        record = parse_line(GOOD_LINE, 7)
        self.assertIsInstance(record, ParsedRecord)
        self.assertEqual(record.node_id, "TEMP-01")
        self.assertEqual(record.state, 0x0F)
        self.assertAlmostEqual(record.value, 23.54)
        self.assertEqual(record.lineno, 7)
        self.assertEqual(
            record.timestamp,
            datetime(2026, 11, 17, 8, 0, tzinfo=timezone(timedelta(hours=2))),
        )
        # NamedTuple поводиться як звичайний кортеж.
        node, state, value, timestamp, lineno = record
        self.assertEqual((node, state, lineno), ("TEMP-01", 15, 7))

    def test_state_parser(self) -> None:
        self.assertEqual(parse_state("0x0f"), 15)
        self.assertEqual(parse_state("FF"), 255)
        with self.assertRaises(InvalidState):
            parse_state("0x100")
        with self.assertRaises(InvalidState):
            parse_state("xyz")

    def test_value_parser(self) -> None:
        self.assertEqual(parse_value("-12.5e2"), -1250.0)
        self.assertEqual(parse_value(".5"), 0.5)
        with self.assertRaises(InvalidValue):
            parse_value("nan")
        with self.assertRaises(InvalidValue):
            parse_value("12,5")

    def test_timestamp_parser_supports_z_suffix(self) -> None:
        moment = parse_timestamp("2026-11-17T08:00:00Z")
        self.assertEqual(moment.tzinfo, UTC)
        self.assertEqual(moment.hour, 8)

    def test_malformed_lines(self) -> None:
        bad_lines = [
            "TEMP-01;0x01;23.5",  # бракує поля
            "TEMP-01;0x01;23.5;2026-11-17",  # немає часу
            "temp-01;0x01;23.5;2026-11-17T08:00:00",  # lower-case вузол
            "TEMP-01 0x01 23.5 2026-11-17T08:00:00",  # невірний розділювач
            "TEMP-01;0x1;23.5;2026-11-17T08:00:00",  # байт не з двох цифр
        ]
        for line in bad_lines:
            with self.subTest(line=line), self.assertRaises(MalformedRecord):
                parse_line(line, 1)

    def test_comment_and_blank_lines_are_skipped(self) -> None:
        text = "\n# comment\n" + GOOD_LINE + "\n"
        records = list(iter_records(text.splitlines()))
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].node_id, "TEMP-01")

    def test_errors_are_collected_without_stopping(self) -> None:
        text = [
            GOOD_LINE,
            "TEMP-01;0xZZ;1.0;2026-11-17T08:00:00",
            GOOD_LINE,
        ]
        errors: list[RecordError] = []
        records = list(iter_records(text, errors=errors))
        self.assertEqual(len(records), 2)
        self.assertEqual(len(errors), 1)
        self.assertIn("рядок 2", str(errors[0]))

    def test_strict_mode_raises(self) -> None:
        with self.assertRaises(MalformedRecord):
            list(iter_records(["TEMP-01;0x01"], strict=True))


if __name__ == "__main__":
    unittest.main()
