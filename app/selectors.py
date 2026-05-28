"""Functions that build Dash dropdown option lists for each selector.

All functions return lists of {"label": str, "value": ...} dicts.
Network-dependent options (vintages, scopes, sumlevels, groups) are wrapped
in try/except so the app degrades gracefully when the Census API is unreachable.
"""

from __future__ import annotations

import logging
from functools import lru_cache

from morpc_census.api import Endpoint
from morpc_census.constants import HIGHLEVEL_GROUP_DESC

SURVEY = "acs/acs5"
_DEFAULT_LATEST_VINTAGE = 2024

logger = logging.getLogger(__name__)


def topic_options() -> list[dict]:
    """Options from HIGHLEVEL_GROUP_DESC — no network call required."""
    return [{"label": label, "value": code} for code, label in HIGHLEVEL_GROUP_DESC.items()]


@lru_cache(maxsize=1)
def vintage_options() -> list[dict]:
    """All available vintages for the ACS 5-year survey, newest first."""
    try:
        ep = Endpoint(SURVEY, _DEFAULT_LATEST_VINTAGE)
        return [{"label": str(y), "value": y} for y in sorted(ep.vintages, reverse=True)]
    except Exception:
        logger.warning("Could not fetch vintages from Census API; using fallback range.")
        return [{"label": str(y), "value": y} for y in range(2024, 2008, -1)]


def _scope_label(key: str, scope) -> str:
    """Return a display label like 'County: Franklin' derived from scope metadata."""
    for_param = getattr(scope, "for_param", "") or ""
    geo_type = for_param.split(":")[0].strip().lower() if ":" in for_param else ""
    values_part = for_param.split(":", 1)[-1] if ":" in for_param else ""
    is_multi = "," in values_part

    if geo_type == "us":
        return "National"
    if geo_type == "state":
        return f"State: {key.replace('_', ' ').title()}"
    if geo_type == "county" and not is_multi:
        return f"County: {key.replace('_', ' ').title()}"
    if geo_type == "county" and is_multi:
        if key.startswith("region"):
            suffix = key[len("region"):]
            name = f"{suffix}-County" if suffix.isdigit() else suffix.upper()
        else:
            name = key.replace("_", " ").title()
        return f"Region: {name}"
    if "metropolitan" in geo_type or "micropolitan" in geo_type:
        name = key.replace("cbsa", "").replace("_", " ").strip().title()
        return f"Metro Area: {name}"
    # Fallback: capitalise the key
    return key.replace("_", " ").title()


@lru_cache(maxsize=1)
def _scopes_map():
    """Return the SCOPES dict, or {} if unavailable."""
    try:
        from morpc_census.geos import SCOPES
        return SCOPES
    except Exception:
        return {}


def scope_label(key: str) -> str:
    """Return the friendly display label for a scope key."""
    scopes = _scopes_map()
    if key in scopes:
        return _scope_label(key, scopes[key])
    return key.replace("_", " ").title()


def scope_title_name(key: str) -> str:
    """Return a natural-language geo name for use in chart titles."""
    scopes = _scopes_map()
    if key not in scopes:
        return key.replace("_", " ").title()
    scope = scopes[key]
    for_param = getattr(scope, "for_param", "") or ""
    geo_type = for_param.split(":")[0].strip().lower() if ":" in for_param else ""
    values_part = for_param.split(":", 1)[-1] if ":" in for_param else ""
    is_multi = "," in values_part
    name = key.replace("_", " ").title()
    if geo_type == "us":
        return "the United States"
    if geo_type == "state":
        return name
    if geo_type == "county" and not is_multi:
        return f"{name} County"
    if geo_type == "county" and is_multi:
        if key.startswith("region"):
            suffix = key[len("region"):]
            return f"{suffix}-County Region" if suffix.isdigit() else f"{suffix.upper()} Region"
        return f"{name} Region"
    if "metropolitan" in geo_type or "micropolitan" in geo_type:
        cbsa_name = key.replace("cbsa", "").replace("_", " ").strip().title()
        return f"{cbsa_name} Metro Area"
    return name


def _scope_sort_key(key: str, scope) -> tuple[int, str]:
    """Return (category_order, key) so scopes sort as Region, CBSA, Counties, States, US."""
    for_param = getattr(scope, "for_param", "") or ""
    geo_type = for_param.split(":")[0].strip().lower() if ":" in for_param else ""
    values_part = for_param.split(":", 1)[-1] if ":" in for_param else ""
    is_multi = "," in values_part
    if geo_type == "county" and is_multi:
        return (0, key)
    if "metropolitan" in geo_type or "micropolitan" in geo_type:
        return (1, key)
    if geo_type == "county" and not is_multi:
        return (2, key)
    if geo_type == "state":
        return (3, key)
    if geo_type == "us":
        return (4, key)
    return (5, key)


@lru_cache(maxsize=1)
def scope_options() -> list[dict]:
    """All named scopes from morpc.SCOPES, ordered Region → CBSA → Counties → States → US."""
    try:
        scopes = _scopes_map()
        if not scopes:
            raise ValueError("empty")
        return [
            {"label": _scope_label(k, scopes[k]), "value": k}
            for k in sorted(scopes.keys(), key=lambda k: _scope_sort_key(k, scopes[k]))
        ]
    except Exception:
        logger.warning("Could not load scope options from morpc.")
        return []


@lru_cache(maxsize=1)
def sumlevel_options() -> list[dict]:
    """Summary levels from morpc.SUMLEVEL_DESCRIPTIONS that have a name."""
    try:
        from morpc import SUMLEVEL_DESCRIPTIONS
        return [
            {"label": f"{desc.get('singular', code)} ({code})", "value": code}
            for code, desc in SUMLEVEL_DESCRIPTIONS.items()
            if desc.get("singular") and not code.startswith("M")
        ]
    except Exception:
        logger.warning("Could not load sumlevel options from morpc.")
        return []


@lru_cache(maxsize=len(HIGHLEVEL_GROUP_DESC))
def group_options_for_topic(topic_code: str, vintage: int = _DEFAULT_LATEST_VINTAGE) -> list[dict]:
    """Groups matching a topic's two-digit prefix, fetched from the Census API.

    Group codes have the form ``B01001`` where ``[1:3]`` gives the topic prefix.
    Results are cached per topic_code + vintage to avoid redundant API calls.
    Returns an empty list (with an error option) if the API is unreachable.
    """
    try:
        ep = Endpoint(SURVEY, vintage)
        matching = {
            code: meta
            for code, meta in ep.groups.items()
            if len(code) >= 3 and code[1:3] == topic_code
        }
        return [
            {"label": f"{code} — {meta.get('description', code)}", "value": code}
            for code, meta in sorted(matching.items())
        ]
    except Exception:
        logger.warning(f"Could not fetch groups for topic {topic_code!r}.")
        return []
