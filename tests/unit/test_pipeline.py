"""Unit tests for import pipeline utilities.

Covers ``ImportReport`` and ``_ffprobe_available`` — pure logic
that does not require a database or temporary files.
"""

from __future__ import annotations

from unittest.mock import patch

from filmoteka.domain.importing.pipeline import ImportReport, _ffprobe_available


class TestImportReportDefaults:
    """ImportReport with no arguments."""

    def test_defaults(self) -> None:
        report = ImportReport()
        assert report.files_found == 0
        assert report.files_probed == 0
        assert report.files_indexed == 0
        assert report.films_created == 0
        assert report.errors == []

    def test_to_dict(self) -> None:
        report = ImportReport()
        d = report.to_dict()
        assert d["files_found"] == 0
        assert d["files_probed"] == 0
        assert d["files_indexed"] == 0
        assert d["films_created"] == 0
        assert d["errors"] == []

    def test_to_dict_after_run(self) -> None:
        report = ImportReport(files_found=3, files_probed=2, files_indexed=2, films_created=2)
        d = report.to_dict()
        assert d["files_found"] == 3
        assert d["files_probed"] == 2
        assert d["files_indexed"] == 2
        assert d["films_created"] == 2
        assert d["errors"] == []

    def test_to_dict_with_errors(self) -> None:
        report = ImportReport(errors=["err1", "err2"])
        d = report.to_dict()
        assert d["errors"] == ["err1", "err2"]

    def test_errors_default_is_new_list(self) -> None:
        r1 = ImportReport()
        r2 = ImportReport()
        assert r1.errors is not r2.errors


class TestFfprobeAvailable:
    """_ffprobe_available — shutil.which probe."""

    def test_ffprobe_found(self) -> None:
        target = "filmoteka.domain.importing.pipeline.shutil.which"
        with patch(target, return_value="/usr/bin/ffprobe"):
            assert _ffprobe_available() is True

    def test_ffprobe_not_found(self) -> None:
        target = "filmoteka.domain.importing.pipeline.shutil.which"
        with patch(target, return_value=None):
            assert _ffprobe_available() is False
