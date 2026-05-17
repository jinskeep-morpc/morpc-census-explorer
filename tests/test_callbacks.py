"""Unit tests for callback logic in app/callbacks.py."""

import pandas as pd
import pytest
from unittest.mock import MagicMock, patch

from app.callbacks import (
    _friendly_error,
    compute_fetch_and_store,
    compute_fetch_button_disabled,
    compute_group_options,
)


class TestComputeGroupOptions:
    def test_no_topic_returns_disabled(self):
        options, value, disabled = compute_group_options(None)
        assert options == []
        assert value is None
        assert disabled is True

    def test_topic_enables_dropdown(self):
        grps = [{"label": "B01001 — Sex by Age", "value": "B01001"}]
        with patch("app.callbacks.group_options_for_topic", return_value=grps):
            options, value, disabled = compute_group_options("01")
        assert disabled is False
        assert options == grps

    def test_topic_resets_value_to_none(self):
        with patch("app.callbacks.group_options_for_topic", return_value=[{"label": "X", "value": "X"}]):
            _, value, _ = compute_group_options("01")
        assert value is None

    def test_empty_topic_string_disables(self):
        options, value, disabled = compute_group_options("")
        assert disabled is True


class TestComputeFetchButtonDisabled:
    _ALL = ("01", "B01001", [2023], "franklin", "140")

    def test_disabled_when_all_none(self):
        assert compute_fetch_button_disabled(None, None, None, None, None) is True

    def test_enabled_when_all_provided(self):
        assert compute_fetch_button_disabled(*self._ALL) is False

    def test_disabled_when_vintages_empty_list(self):
        assert compute_fetch_button_disabled("01", "B01001", [], "franklin", "140") is True

    def test_disabled_when_sumlevel_missing(self):
        assert compute_fetch_button_disabled("01", "B01001", [2023], "franklin", None) is True

    def test_disabled_when_scope_missing(self):
        assert compute_fetch_button_disabled("01", "B01001", [2023], None, "140") is True

    def test_disabled_when_group_missing(self):
        assert compute_fetch_button_disabled("01", None, [2023], "franklin", "140") is True

    def test_disabled_when_topic_missing(self):
        assert compute_fetch_button_disabled(None, "B01001", [2023], "franklin", "140") is True

    def test_multiple_vintages_still_enabled(self):
        assert compute_fetch_button_disabled("01", "B01001", [2023, 2022], "franklin", "140") is False


# ---------------------------------------------------------------------------
# _friendly_error
# ---------------------------------------------------------------------------

class TestFriendlyError:
    def test_operational_error_message(self):
        exc = Exception("OperationalError: could not connect to server")
        # match by class name check
        class OperationalError(Exception): pass
        result = _friendly_error(OperationalError("could not connect"))
        assert "database" in result.lower() or "connection" in result.lower()

    def test_timeout_message(self):
        class TimeoutError(Exception): pass
        result = _friendly_error(TimeoutError("request timed out"))
        assert "timeout" in result.lower() or "timed out" in result.lower()

    def test_generic_exception_includes_type_name(self):
        class WeirdError(Exception): pass
        result = _friendly_error(WeirdError("something broke"))
        assert "WeirdError" in result


# ---------------------------------------------------------------------------
# compute_fetch_and_store (4-tuple return)
# ---------------------------------------------------------------------------

def _make_long():
    return pd.DataFrame([{
        "geoidfq": "050US39049",
        "name": "Franklin County",
        "reference_period": 2023,
        "survey": "acs/acs5",
        "concept": "Sex by Age",
        "universe": "Total population",
        "variable_label": "Total",
        "variable": "B01001_001",
        "estimate": 1_300_000.0,
        "moe": 50_000.0,
    }])


class TestComputeFetchAndStore:
    def _mock_session(self):
        return MagicMock()

    def test_returns_four_tuple(self):
        with patch("app.callbacks.SessionLocal", return_value=self._mock_session()), \
             patch("app.callbacks.fetch_all_vintages", return_value=_make_long()):
            result = compute_fetch_and_store(1, "B01001", [2023], "franklin", "140")
        assert len(result) == 4

    def test_success_returns_store_and_status(self):
        with patch("app.callbacks.SessionLocal", return_value=self._mock_session()), \
             patch("app.callbacks.fetch_all_vintages", return_value=_make_long()):
            store, status, err_msg, err_open = compute_fetch_and_store(1, "B01001", [2023], "franklin", "140")
        assert store is not None
        assert "B01001" in status
        assert err_open is False

    def test_exception_opens_alert(self):
        with patch("app.callbacks.SessionLocal", return_value=self._mock_session()), \
             patch("app.callbacks.fetch_all_vintages", side_effect=RuntimeError("boom")):
            store, status, err_msg, err_open = compute_fetch_and_store(1, "B01001", [2023], "franklin", "140")
        assert err_open is True
        assert "RuntimeError" in err_msg or "boom" in err_msg

    def test_empty_dataframe_opens_alert(self):
        with patch("app.callbacks.SessionLocal", return_value=self._mock_session()), \
             patch("app.callbacks.fetch_all_vintages", return_value=pd.DataFrame()):
            store, status, err_msg, err_open = compute_fetch_and_store(1, "B01001", [2023], "franklin", "140")
        assert err_open is True
        assert "No data" in err_msg
