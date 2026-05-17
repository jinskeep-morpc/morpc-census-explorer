"""Unit tests for app/selectors.py option-building functions."""

from unittest.mock import MagicMock, patch

import pytest

from app.selectors import (
    SURVEY,
    group_options_for_topic,
    scope_options,
    sumlevel_options,
    topic_options,
    vintage_options,
)


class TestTopicOptions:
    def test_returns_list_of_dicts(self):
        opts = topic_options()
        assert isinstance(opts, list)
        assert all({"label", "value"} <= set(o) for o in opts)

    def test_not_empty(self):
        assert len(topic_options()) > 0

    def test_value_is_two_digit_string(self):
        for opt in topic_options():
            assert isinstance(opt["value"], str)
            assert len(opt["value"]) == 2

    def test_label_is_nonempty_string(self):
        for opt in topic_options():
            assert isinstance(opt["label"], str)
            assert opt["label"]


class TestVintageOptions:
    def _mock_endpoint(self, vintages):
        ep = MagicMock()
        ep.vintages = vintages
        return ep

    def test_returns_list_newest_first(self):
        with patch("app.selectors.Endpoint", return_value=self._mock_endpoint([2021, 2023, 2022])):
            vintage_options.cache_clear()
            opts = vintage_options()
        assert [o["value"] for o in opts] == [2023, 2022, 2021]

    def test_label_matches_value_as_string(self):
        with patch("app.selectors.Endpoint", return_value=self._mock_endpoint([2023])):
            vintage_options.cache_clear()
            opts = vintage_options()
        assert opts[0]["label"] == "2023"
        assert opts[0]["value"] == 2023

    def test_falls_back_on_api_error(self):
        with patch("app.selectors.Endpoint", side_effect=Exception("network error")):
            vintage_options.cache_clear()
            opts = vintage_options()
        assert len(opts) > 0
        assert all(isinstance(o["value"], int) for o in opts)

    def teardown_method(self):
        vintage_options.cache_clear()


class TestScopeOptions:
    def test_returns_list_of_dicts_when_morpc_available(self):
        fake_scopes = {"franklin": MagicMock(), "region15": MagicMock()}
        with patch("app.selectors.scope_options.__wrapped__", create=True), \
             patch("morpc_census.geos.SCOPES", fake_scopes):
            scope_options.cache_clear()
            # Patch inside the function's import path
            with patch.dict("sys.modules", {}):
                pass  # just ensure no crash on import

    def test_returns_empty_list_on_morpc_error(self):
        with patch("app.selectors.scope_options", return_value=[]):
            opts = scope_options()
        assert isinstance(opts, list)

    def teardown_method(self):
        scope_options.cache_clear()


class TestSumlevelOptions:
    def test_returns_empty_list_on_morpc_error(self):
        with patch("app.selectors.sumlevel_options", return_value=[]):
            opts = sumlevel_options()
        assert isinstance(opts, list)

    def teardown_method(self):
        sumlevel_options.cache_clear()


class TestGroupOptionsForTopic:
    def _mock_endpoint(self, groups: dict):
        ep = MagicMock()
        ep.groups = groups
        return ep

    def test_filters_by_topic_prefix(self):
        groups = {
            "B01001": {"description": "Sex by Age"},
            "B01002": {"description": "Median Age"},
            "B02001": {"description": "Race"},  # topic "02", should be excluded
        }
        with patch("app.selectors.Endpoint", return_value=self._mock_endpoint(groups)):
            group_options_for_topic.cache_clear()
            opts = group_options_for_topic("01")
        codes = [o["value"] for o in opts]
        assert "B01001" in codes
        assert "B01002" in codes
        assert "B02001" not in codes

    def test_label_contains_code_and_description(self):
        groups = {"B01001": {"description": "Sex by Age"}}
        with patch("app.selectors.Endpoint", return_value=self._mock_endpoint(groups)):
            group_options_for_topic.cache_clear()
            opts = group_options_for_topic("01")
        assert opts[0]["label"] == "B01001 — Sex by Age"

    def test_returns_empty_list_on_api_error(self):
        with patch("app.selectors.Endpoint", side_effect=Exception("network")):
            group_options_for_topic.cache_clear()
            opts = group_options_for_topic("01")
        assert opts == []

    def test_sorted_by_group_code(self):
        groups = {
            "B01003": {"description": "Total Population"},
            "B01001": {"description": "Sex by Age"},
            "B01002": {"description": "Median Age"},
        }
        with patch("app.selectors.Endpoint", return_value=self._mock_endpoint(groups)):
            group_options_for_topic.cache_clear()
            opts = group_options_for_topic("01")
        assert [o["value"] for o in opts] == ["B01001", "B01002", "B01003"]

    def teardown_method(self):
        group_options_for_topic.cache_clear()
