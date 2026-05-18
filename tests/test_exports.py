"""Unit tests for app/exports.py and export callback logic."""

from __future__ import annotations

import io
import zipfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from app.callbacks import compute_excel_download, compute_frictionless_download
from app.exports import export_excel, export_frictionless
from app.fetch import serialise_long


# ---------------------------------------------------------------------------
# Helpers / shared constants
# ---------------------------------------------------------------------------

_SCOPE = "franklin"
_SUMLEVEL = "050"


def _make_long(vintage=2023):
    return pd.DataFrame([
        {
            "geoidfq": "050US39049",
            "name": "Franklin County",
            "reference_period": vintage,
            "survey": "acs/acs5",
            "concept": "Sex by Age",
            "universe": "Total population",
            "variable_label": "Total",
            "variable": "B01001_001",
            "estimate": 1_300_000.0,
            "moe": 50_000.0,
        },
        {
            "geoidfq": "050US39049",
            "name": "Franklin County",
            "reference_period": vintage,
            "survey": "acs/acs5",
            "concept": "Sex by Age",
            "universe": "Total population",
            "variable_label": "Male",
            "variable": "B01001_002",
            "estimate": 640_000.0,
            "moe": 20_000.0,
        },
    ])


class _FakeExcelChart:
    """xlsxwriter-backed stand-in for morpc.plot.excel.ExcelChart used in tests."""

    def __init__(self, df: pd.DataFrame, buf, sheetname: str) -> None:
        self._df = df
        self._buf = buf
        self._sheet = sheetname[:31]

    def write(self) -> None:
        with pd.ExcelWriter(self._buf, engine="xlsxwriter") as writer:
            self._df.to_excel(writer, sheet_name=self._sheet, merge_cells=True)


def _mock_census_api(group_code: str = "B01001", vintage: int = 2023) -> MagicMock:
    """Return a CensusAPI mock that writes placeholder files on save()."""
    name = f"census-acs5-acs5-{vintage}-{_SUMLEVEL}-{_SCOPE}-{group_code.lower()}"
    mock_api = MagicMock()
    mock_api.filename = f"{name}.long.csv"

    def _fake_save(outdir):
        d = Path(outdir)
        (d / mock_api.filename).write_text("placeholder\n")
        (d / f"{name}.schema.yaml").write_text("fields: []\n")
        (d / f"{name}.resource.yaml").write_text("name: test\n")

    mock_api.save.side_effect = _fake_save
    return mock_api


def _export_frictionless_mocked(df, group_code="B01001", vintages=None):
    """Call export_frictionless with CensusAPI/Endpoint/Group mocked out."""
    if vintages is None:
        vintages = [2023]
    vintage = sorted(vintages)[0]
    mock_api = _mock_census_api(group_code, vintage)
    with patch("app.exports.CensusAPI", return_value=mock_api), \
         patch("app.exports.Endpoint"), \
         patch("app.exports.Group"):
        return export_frictionless(df, group_code, vintages, _SCOPE, _SUMLEVEL)


# ---------------------------------------------------------------------------
# export_frictionless
# ---------------------------------------------------------------------------

class TestExportFrictionless:
    def test_returns_bytes(self):
        result = _export_frictionless_mocked(_make_long())
        assert isinstance(result, bytes)
        assert len(result) > 0

    def test_result_is_valid_zip(self):
        result = _export_frictionless_mocked(_make_long())
        assert zipfile.is_zipfile(io.BytesIO(result))

    def test_zip_contains_csv(self):
        result = _export_frictionless_mocked(_make_long())
        with zipfile.ZipFile(io.BytesIO(result)) as zf:
            names = zf.namelist()
        assert any(n.endswith(".long.csv") for n in names)

    def test_zip_contains_schema_yaml(self):
        result = _export_frictionless_mocked(_make_long())
        with zipfile.ZipFile(io.BytesIO(result)) as zf:
            names = zf.namelist()
        assert any(n.endswith(".schema.yaml") for n in names)

    def test_zip_contains_resource_yaml(self):
        result = _export_frictionless_mocked(_make_long())
        with zipfile.ZipFile(io.BytesIO(result)) as zf:
            names = zf.namelist()
        assert any(n.endswith(".resource.yaml") for n in names)

    def test_csv_contains_all_rows(self):
        df = _make_long()
        result = _export_frictionless_mocked(df)
        with zipfile.ZipFile(io.BytesIO(result)) as zf:
            csv_name = next(n for n in zf.namelist() if n.endswith(".long.csv"))
            csv_bytes = zf.read(csv_name)
        restored = pd.read_csv(io.BytesIO(csv_bytes))
        assert len(restored) == len(df)

    def test_filename_includes_group_code(self):
        result = _export_frictionless_mocked(_make_long(), "B01001", [2023])
        with zipfile.ZipFile(io.BytesIO(result)) as zf:
            names = zf.namelist()
        assert any("b01001" in n for n in names)

    def test_multi_vintage_csv_has_combined_rows(self):
        df = pd.concat([_make_long(2022), _make_long(2023)], ignore_index=True)
        result = _export_frictionless_mocked(df, "B01001", [2022, 2023])
        with zipfile.ZipFile(io.BytesIO(result)) as zf:
            csv_name = next(n for n in zf.namelist() if n.endswith(".long.csv"))
            restored = pd.read_csv(io.BytesIO(zf.read(csv_name)))
        assert len(restored) == len(df)

    def test_censusapi_called_with_first_vintage(self):
        df = _make_long()
        mock_api = _mock_census_api("B01001", 2022)
        with patch("app.exports.CensusAPI", return_value=mock_api) as mock_cls, \
             patch("app.exports.Endpoint") as mock_ep, \
             patch("app.exports.Group"):
            export_frictionless(df, "B01001", [2022, 2023], _SCOPE, _SUMLEVEL)
        mock_ep.assert_called_once_with("acs/acs5", 2022)


# ---------------------------------------------------------------------------
# export_excel
# ---------------------------------------------------------------------------

class TestExportExcel:
    def test_returns_bytes(self):
        with patch("app.exports.ExcelChart", _FakeExcelChart):
            result = export_excel(_make_long(), "B01001", ["estimate"])
        assert isinstance(result, bytes)
        assert len(result) > 0

    def test_result_is_valid_xlsx(self):
        with patch("app.exports.ExcelChart", _FakeExcelChart):
            result = export_excel(_make_long(), "B01001", ["estimate"])
        assert result[:2] == b"PK"

    def test_multiple_value_types(self):
        with patch("app.exports.ExcelChart", _FakeExcelChart):
            result = export_excel(_make_long(), "B01001", ["estimate", "moe"])
        assert isinstance(result, bytes)
        assert len(result) > 0

    def test_sheet_name_truncated_to_31_chars(self):
        long_code = "B" + "0" * 31  # 32 chars
        with patch("app.exports.ExcelChart", _FakeExcelChart):
            result = export_excel(_make_long(), long_code, ["estimate"])
        assert isinstance(result, bytes)
        assert len(result) > 0

    def test_raises_when_exclechart_unavailable(self):
        with patch("app.exports.ExcelChart", None):
            with pytest.raises(RuntimeError, match="ExcelChart is not available"):
                export_excel(_make_long(), "B01001", ["estimate"])


# ---------------------------------------------------------------------------
# compute_frictionless_download
# ---------------------------------------------------------------------------

_GEO_LIST = [{"scope": _SCOPE, "sumlevel": _SUMLEVEL}]


class TestComputeFrictionlessDownload:
    def test_returns_no_update_when_no_store(self):
        from dash import no_update
        result = compute_frictionless_download(None, "B01001", [2023], _GEO_LIST)
        assert result is no_update

    def test_returns_no_update_when_no_group(self):
        from dash import no_update
        store = serialise_long(_make_long())
        result = compute_frictionless_download(store, None, [2023], _GEO_LIST)
        assert result is no_update

    def test_returns_no_update_when_geo_list_empty(self):
        from dash import no_update
        store = serialise_long(_make_long())
        result = compute_frictionless_download(store, "B01001", [2023], [])
        assert result is no_update

    def test_returns_download_dict_on_success(self):
        store = serialise_long(_make_long())
        mock_api = _mock_census_api()
        with patch("app.exports.CensusAPI", return_value=mock_api), \
             patch("app.exports.Endpoint"), \
             patch("app.exports.Group"):
            result = compute_frictionless_download(store, "B01001", [2023], _GEO_LIST)
        assert isinstance(result, dict)
        assert result["filename"].endswith(".zip")
        assert "base64" in result

    def test_filename_includes_group_and_vintage(self):
        store = serialise_long(_make_long())
        mock_api = _mock_census_api()
        with patch("app.exports.CensusAPI", return_value=mock_api), \
             patch("app.exports.Endpoint"), \
             patch("app.exports.Group"):
            result = compute_frictionless_download(store, "B01001", [2023], _GEO_LIST)
        assert "b01001" in result["filename"]
        assert "2023" in result["filename"]


# ---------------------------------------------------------------------------
# compute_excel_download
# ---------------------------------------------------------------------------

class TestComputeExcelDownload:
    def test_returns_no_update_when_no_store(self):
        from dash import no_update
        result = compute_excel_download(None, "B01001", ["estimate"], [2023])
        assert result is no_update

    def test_returns_no_update_when_no_value_types(self):
        from dash import no_update
        store = serialise_long(_make_long())
        result = compute_excel_download(store, "B01001", [], [2023])
        assert result is no_update

    def test_returns_download_dict_on_success(self):
        store = serialise_long(_make_long())
        with patch("app.exports.ExcelChart", _FakeExcelChart):
            result = compute_excel_download(store, "B01001", ["estimate"], [2023])
        assert isinstance(result, dict)
        assert result["filename"].endswith(".xlsx")
        assert "base64" in result

    def test_filename_includes_group_and_vintage(self):
        store = serialise_long(_make_long())
        with patch("app.exports.ExcelChart", _FakeExcelChart):
            result = compute_excel_download(store, "B01001", ["estimate"], [2022, 2023])
        assert "b01001" in result["filename"]
        assert "2022" in result["filename"]
