"""Unit tests for app/exports.py and export callback logic."""

import io
import zipfile
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from app.callbacks import compute_excel_download, compute_frictionless_download
from app.exports import export_excel, export_frictionless
from app.fetch import serialise_long


# ---------------------------------------------------------------------------
# Fixture
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# export_frictionless
# ---------------------------------------------------------------------------

class TestExportFrictionless:
    def test_returns_bytes(self):
        result = export_frictionless(_make_long(), "B01001", [2023])
        assert isinstance(result, bytes)
        assert len(result) > 0

    def test_result_is_valid_zip(self):
        result = export_frictionless(_make_long(), "B01001", [2023])
        assert zipfile.is_zipfile(io.BytesIO(result))

    def test_zip_contains_csv(self):
        result = export_frictionless(_make_long(), "B01001", [2023])
        with zipfile.ZipFile(io.BytesIO(result)) as zf:
            names = zf.namelist()
        assert any(n.endswith(".long.csv") for n in names)

    def test_zip_contains_schema_yaml(self):
        result = export_frictionless(_make_long(), "B01001", [2023])
        with zipfile.ZipFile(io.BytesIO(result)) as zf:
            names = zf.namelist()
        assert any(n.endswith(".schema.yaml") for n in names)

    def test_zip_contains_resource_yaml(self):
        result = export_frictionless(_make_long(), "B01001", [2023])
        with zipfile.ZipFile(io.BytesIO(result)) as zf:
            names = zf.namelist()
        assert any(n.endswith(".resource.yaml") for n in names)

    def test_csv_contains_all_rows(self):
        df = _make_long()
        result = export_frictionless(df, "B01001", [2023])
        with zipfile.ZipFile(io.BytesIO(result)) as zf:
            csv_name = next(n for n in zf.namelist() if n.endswith(".long.csv"))
            csv_bytes = zf.read(csv_name)
        restored = pd.read_csv(io.BytesIO(csv_bytes))
        assert len(restored) == len(df)

    def test_filename_includes_group_and_vintages(self):
        result = export_frictionless(_make_long(), "B01001", [2022, 2023])
        with zipfile.ZipFile(io.BytesIO(result)) as zf:
            names = zf.namelist()
        assert any("b01001" in n and "2022" in n and "2023" in n for n in names)

    def test_multi_vintage_concatenated(self):
        df = pd.concat([_make_long(2022), _make_long(2023)], ignore_index=True)
        result = export_frictionless(df, "B01001", [2022, 2023])
        with zipfile.ZipFile(io.BytesIO(result)) as zf:
            csv_name = next(n for n in zf.namelist() if n.endswith(".long.csv"))
            restored = pd.read_csv(io.BytesIO(zf.read(csv_name)))
        assert len(restored) == len(df)


# ---------------------------------------------------------------------------
# export_excel
# ---------------------------------------------------------------------------

class TestExportExcel:
    def test_returns_bytes(self):
        result = export_excel(_make_long(), "B01001", ["estimate"])
        assert isinstance(result, bytes)
        assert len(result) > 0

    def test_result_is_valid_xlsx(self):
        # xlsx files start with the PK zip magic bytes
        result = export_excel(_make_long(), "B01001", ["estimate"])
        assert result[:2] == b"PK"

    def test_falls_back_to_pandas_when_exclechart_fails(self):
        with patch("app.exports.ExcelChart", side_effect=ImportError("no morpc")):
            result = export_excel(_make_long(), "B01001", ["estimate"])
        assert isinstance(result, bytes)
        assert result[:2] == b"PK"

    def test_multiple_value_types(self):
        result = export_excel(_make_long(), "B01001", ["estimate", "moe"])
        assert isinstance(result, bytes)
        assert len(result) > 0


# ---------------------------------------------------------------------------
# compute_frictionless_download
# ---------------------------------------------------------------------------

class TestComputeFrictionlessDownload:
    def test_returns_no_update_when_no_store(self):
        from dash import no_update
        result = compute_frictionless_download(None, "B01001", [2023])
        assert result is no_update

    def test_returns_no_update_when_no_group(self):
        from dash import no_update
        store = serialise_long(_make_long())
        result = compute_frictionless_download(store, None, [2023])
        assert result is no_update

    def test_returns_download_dict_on_success(self):
        store = serialise_long(_make_long())
        result = compute_frictionless_download(store, "B01001", [2023])
        assert isinstance(result, dict)
        assert result["filename"].endswith(".zip")
        assert "base64" in result

    def test_filename_includes_group_and_vintage(self):
        store = serialise_long(_make_long())
        result = compute_frictionless_download(store, "B01001", [2023])
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
        result = compute_excel_download(store, "B01001", ["estimate"], [2023])
        assert isinstance(result, dict)
        assert result["filename"].endswith(".xlsx")
        assert "base64" in result

    def test_filename_includes_group_and_vintage(self):
        store = serialise_long(_make_long())
        result = compute_excel_download(store, "B01001", ["estimate"], [2022, 2023])
        assert "b01001" in result["filename"]
        assert "2022" in result["filename"]
