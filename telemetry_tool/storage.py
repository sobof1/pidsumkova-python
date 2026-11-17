"""Безпечна робота з файловою системою (шаблон RAII).

Класи :class:`TelemetryLog` і :class:`ReportWriter` є менеджерами
контексту: дескриптор відкривається в ``__enter__`` і гарантовано
закривається в ``__exit__`` навіть у разі винятку в тілі ``with``.
Це і є Python-відповідник RAII: час життя ресурсу прив'язаний до
області видимості.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from types import TracebackType

from .exceptions import LogOpenError, LogReadError, RecordError, ReportWriteError
from .parser import ParsedRecord, iter_records

__all__ = ["TelemetryLog", "ReportWriter", "LogSummary"]


class TelemetryLog:
    """Потоковий читач журналу телеметрії.

    Приклад::

        with TelemetryLog("telemetry.log") as log:
            for record in log:
                ...
        print(log.errors)  # пошкоджені рядки, які було пропущено
    """

    def __init__(
        self,
        path: str | Path,
        *,
        encoding: str = "utf-8",
        strict: bool = False,
    ) -> None:
        """Зберігає параметри; файл відкривається лише в ``__enter__``."""
        self._path = Path(path)
        self._encoding = encoding
        self._strict = strict
        self._handle = None
        self.errors: list[RecordError] = []
        self.read_count = 0

    @property
    def path(self) -> Path:
        """Шлях до журналу."""
        return self._path

    @property
    def line_count(self) -> int:
        """Кількість успішно прочитаних записів."""
        return self.read_count

    def __enter__(self) -> TelemetryLog:
        """Відкриває журнал і повертає сам читач."""
        try:
            self._handle = self._path.open("r", encoding=self._encoding)
        except OSError as exc:
            raise LogOpenError(
                f"не вдалося відкрити журнал {self._path}: {exc.strerror or exc}"
            ) from exc
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> bool:
        """Закриває дескриптор; виняток тіла ``with`` не придушує."""
        handle, self._handle = self._handle, None
        if handle is not None:
            handle.close()
        return False

    def __iter__(self) -> Iterator[ParsedRecord]:
        """Ітерує валідні записи, накопичуючи помилки у :attr:`errors`."""
        if self._handle is None:
            raise LogReadError("журнал не відкрито: використовуйте менеджер контексту")
        try:
            for record in iter_records(
                self._handle,
                errors=self.errors,
                strict=self._strict,
            ):
                self.read_count += 1
                yield record
        except OSError as exc:
            raise LogReadError(
                f"помилка читання {self._path}: {exc.strerror or exc}"
            ) from exc

    def summary(self) -> LogSummary:
        """Підсумок читання (для звіту)."""
        return LogSummary(
            path=str(self._path),
            accepted=self.read_count,
            rejected=len(self.errors),
        )


class LogSummary:
    """Незмінний підсумок обробки журналу."""

    __slots__ = ("path", "accepted", "rejected")

    def __init__(self, path: str, accepted: int, rejected: int) -> None:
        """Зберігає шлях і лічильники прийнятих/відхилених записів."""
        self.path = path
        self.accepted = accepted
        self.rejected = rejected


class ReportWriter:
    """Менеджер контексту для атомарного запису звіту.

    Текст пишеться у тимчасовий файл ``*.tmp`` і лише після успішного
    закриття перейменовується на цільовий. Так пошкоджений звіт не
    залишається на диску.
    """

    def __init__(self, path: str | Path, *, encoding: str = "utf-8") -> None:
        """Запам'ятовує цільовий шлях і шлях тимчасового файлу."""
        self._path = Path(path)
        self._tmp_path = self._path.with_name(self._path.name + ".tmp")
        self._encoding = encoding
        self._handle = None
        self._committed = False

    def __enter__(self) -> ReportWriter:
        """Створює тимчасовий файл для звіту."""
        try:
            self._handle = self._tmp_path.open("w", encoding=self._encoding)
        except OSError as exc:
            raise ReportWriteError(
                f"не вдалося створити {self._tmp_path}: {exc.strerror or exc}"
            ) from exc
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> bool:
        """Закриває файл, фіксує або відкочує тимчасовий звіт."""
        handle, self._handle = self._handle, None
        try:
            if handle is not None:
                handle.close()
        except OSError as exc:
            raise ReportWriteError(
                f"не вдалося закрити {self._tmp_path}: {exc.strerror or exc}"
            ) from exc

        if exc_type is not None:
            # Тіло ``with`` впало — прибираємо недописаний файл.
            self._tmp_path.unlink(missing_ok=True)
            return False
        try:
            self._tmp_path.replace(self._path)
            self._committed = True
        except OSError as exc:
            raise ReportWriteError(
                f"не вдалося зберегти звіт {self._path}: {exc.strerror or exc}"
            ) from exc
        return False

    def write(self, text: str) -> int:
        """Записує фрагмент звіту, повертає кількість символів."""
        if self._handle is None:
            raise ReportWriteError(
                "звіт не відкрито: використовуйте менеджер контексту"
            )
        try:
            return self._handle.write(text)
        except OSError as exc:
            raise ReportWriteError(
                f"помилка запису звіту: {exc.strerror or exc}"
            ) from exc

    def writelines(self, lines: list[str]) -> None:
        """Записує список рядків."""
        self.write("".join(lines))
