"""Наскрізні тести командного інтерфейсу."""

from __future__ import annotations

import contextlib
import io
import tempfile
import unittest
from pathlib import Path

from telemetry_tool.cli import main

SAMPLE = Path(__file__).resolve().parents[1] / "data" / "telemetry.log"


class CliTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.dir = Path(self._tmp.name)
        self.report = self.dir / "report.txt"

    def _run(self, *args: str) -> tuple[int, str]:
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            code = main(list(args))
        return code, buffer.getvalue()

    def test_end_to_end_report(self) -> None:
        code, stdout = self._run(str(SAMPLE), "-o", str(self.report), "--quiet")
        self.assertEqual(code, 0)
        self.assertEqual(stdout, "")
        text = self.report.read_text(encoding="utf-8")
        self.assertIn("ЗВІТ ПРО СТАН МЕРЕЖІ МОНІТОРИНГУ", text)
        self.assertIn("TEMP-01", text)
        self.assertIn("PRES-02", text)
        self.assertIn("КРИТИЧНІ ПОДІЇ", text)
        self.assertIn("ДІАГНОСТИКА ВХІДНОГО ЖУРНАЛУ", text)
        self.assertIn("відхилено 6", text)

    def test_missing_input_returns_2(self) -> None:
        code, _ = self._run(str(self.dir / "absent.log"), "--quiet")
        self.assertEqual(code, 2)

    def test_strict_mode_returns_2(self) -> None:
        code, _ = self._run(str(SAMPLE), "-o", str(self.report), "--strict", "--quiet")
        self.assertEqual(code, 2)
        self.assertFalse(self.report.exists())

    def test_critical_only(self) -> None:
        self._run(
            str(SAMPLE),
            "-o",
            str(self.report),
            "--critical-only",
            "--quiet",
        )
        text = self.report.read_text(encoding="utf-8")
        self.assertIn("TEMP-01", text)
        self.assertNotIn("PUMP-01", text)

    def test_node_filter(self) -> None:
        self._run(
            str(SAMPLE),
            "-o",
            str(self.report),
            "--node",
            "PRES-02",
            "--quiet",
        )
        text = self.report.read_text(encoding="utf-8")
        self.assertIn("PRES-02", text)
        self.assertNotIn("TEMP-01", text)

    def test_default_output_name(self) -> None:
        log_copy = self.dir / "copy.log"
        log_copy.write_text(
            "TEMP-01;0x01;20.0;2026-11-17T08:00:00+02:00\n",
            encoding="utf-8",
        )
        code, _ = self._run(str(log_copy), "--quiet")
        self.assertEqual(code, 0)
        self.assertTrue((self.dir / "copy.log.report.txt").exists())


if __name__ == "__main__":
    unittest.main()
