"""Unit tests for callback logic in app/callbacks.py."""

from unittest.mock import patch

from app.callbacks import compute_fetch_button_disabled, compute_group_options


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
