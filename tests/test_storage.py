"""Тести файлових менеджерів контексту."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from telemetry_tool.exceptions import LogOpenError, LogReadError, ReportWriteError
from telemetry_tool.storage import ReportWriter, TelemetryLog

GOOD_LINE = "TEMP-01;0x01;23.50;2026-11-17T08:00:00+02:00\n"
BAD_LINE = "TEMP-01;0x01\n"


class TelemetryLogTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.dir = Path(self._tmp.name)

    def _write_log(self, text: str) -> Path:
        path = self.dir / "test.log"
        path.write_text(text, encoding="utf-8")
        return path

    def test_streams_valid_records_and_collects_errors(self) -> None:
        path = self._write_log(GOOD_LINE + BAD_LINE + GOOD_LINE)
        with TelemetryLog(path) as log:
            records = list(log)
            self.assertEqual(log.line_count, 2)
            summary = log.summary()
        self.assertEqual([r.node_id for r in records], ["TEMP-01", "TEMP-01"])
        self.assertEqual(len(log.errors), 1)
        self.assertEqual(summary.accepted, 2)
        self.assertEqual(summary.rejected, 1)

    def test_missing_file_raises_log_open_error(self) -> None:
        with self.assertRaises(LogOpenError), TelemetryLog(self.dir / "absent.log"):
            pass

    def test_iteration_requires_context_manager(self) -> None:
        log = TelemetryLog(self.dir / "absent.log")
        with self.assertRaises(LogReadError):
            list(log)

    def test_strict_mode_propagates_record_error(self) -> None:
        path = self._write_log(GOOD_LINE + BAD_LINE)
        with (
            self.assertRaises(Exception) as ctx,
            TelemetryLog(path, strict=True) as log,
        ):
            list(log)
        self.assertIn("рядок 2", str(ctx.exception))


class ReportWriterTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.path = Path(self._tmp.name) / "report.txt"

    def test_writes_atomically(self) -> None:
        with ReportWriter(self.path) as writer:
            writer.write("частина 1\n")
            writer.writelines(["частина 2\n", "частина 3\n"])
        self.assertEqual(
            self.path.read_text(encoding="utf-8"),
            "частина 1\nчастина 2\nчастина 3\n",
        )
        self.assertFalse(self.path.with_name("report.txt.tmp").exists())

    def test_exception_discards_temporary_file(self) -> None:
        with self.assertRaises(RuntimeError), ReportWriter(self.path) as writer:
            writer.write("недописаний звіт")
            raise RuntimeError("збій")
        self.assertFalse(self.path.exists())
        self.assertFalse(self.path.with_name("report.txt.tmp").exists())

    def test_write_outside_context_raises(self) -> None:
        with self.assertRaises(ReportWriteError):
            ReportWriter(self.path).write("x")


if __name__ == "__main__":
    unittest.main()
