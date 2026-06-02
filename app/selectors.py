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

SURVEYS = {
    "acs/acs5": {
        "label": "ACS 5-Year Estimates",
        "short": "acs5",
        "default_vintage": 2024,
        "has_moe": True,
        "has_topics": True,
        "source_url": "https://www.census.gov/data/developers/data-sets/acs-5year.html",
    },
    "acs/acs1": {
        "label": "ACS 1-Year Estimates",
        "short": "acs1",
        "default_vintage": 2023,
        "has_moe": True,
        "has_topics": True,
        "source_url": "https://www.census.gov/data/developers/data-sets/acs-1year.html",
    },
    "dec/pl": {
        "label": "Decennial P.L. 94-171 Redistricting Data",
        "short": "dec-pl",
        "default_vintage": 2020,
        "has_moe": False,
        "has_topics": False,
        "source_url": "https://www.census.gov/data/developers/data-sets/decennial-census.html",
    },
    "dec/dhc": {
        "label": "Decennial Demographic and Housing Characteristics",
        "short": "dec-dhc",
        "default_vintage": 2020,
        "has_moe": False,
        "has_topics": False,
        "source_url": "https://www.census.gov/data/developers/data-sets/decennial-census.html",
    },
    "dec/sf1": {
        "label": "Decennial Summary File 1",
        "short": "dec-sf1",
        "default_vintage": 2010,
        "has_moe": False,
        "has_topics": False,
        "source_url": "https://www.census.gov/data/developers/data-sets/decennial-census.html",
    },
}

# backward-compat alias used in a few places
SURVEY = "acs/acs5"

_DEFAULT_LATEST_VINTAGE = 2024

logger = logging.getLogger(__name__)

_DEC_VINTAGE_FALLBACKS: dict[str, list[dict]] = {
    "dec/pl":  [{"label": "2020", "value": 2020}, {"label": "2010", "value": 2010}],
    "dec/dhc": [{"label": "2020", "value": 2020}],
    "dec/sf1": [{"label": "2010", "value": 2010}],
}


def survey_options() -> list[dict]:
    return [{"label": v["label"], "value": k} for k, v in SURVEYS.items()]


@lru_cache(maxsize=len(SURVEYS))
def vintage_options(survey: str = "acs/acs5") -> list[dict]:
    """Available vintages for the given survey, newest first."""
    try:
        default = SURVEYS.get(survey, SURVEYS["acs/acs5"])["default_vintage"]
        ep = Endpoint(survey, default)
        return [{"label": str(y), "value": y} for y in sorted(ep.vintages, reverse=True)]
    except Exception:
        logger.warning("Could not fetch vintages for %s; using fallback.", survey)
        if survey in _DEC_VINTAGE_FALLBACKS:
            return _DEC_VINTAGE_FALLBACKS[survey]
        return [{"label": str(y), "value": y} for y in range(2024, 2008, -1)]


def topic_options(survey: str = "acs/acs5") -> list[dict]:
    """Topic options — empty list for surveys without the ACS topic taxonomy."""
    if not SURVEYS.get(survey, {}).get("has_topics", True):
        return []
    return [{"label": label, "value": code} for code, label in HIGHLEVEL_GROUP_DESC.items()]


@lru_cache(maxsize=500)
def group_options_for_topic(
    topic_code: str | None,
    survey: str = "acs/acs5",
    vintage: int = _DEFAULT_LATEST_VINTAGE,
) -> list[dict]:
    """Groups for a topic (ACS) or all groups (decennial)."""
    try:
        ep = Endpoint(survey, vintage)
        if not SURVEYS.get(survey, {}).get("has_topics", True):
            # Decennial: return all groups
            return [
                {"label": f"{code} — {meta.get('description', code)}", "value": code}
                for code, meta in sorted(ep.groups.items())
            ]
        # ACS: filter by two-digit topic prefix
        if not topic_code:
            return []
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
        logger.warning(
            "Could not fetch groups for topic=%s survey=%s vintage=%s",
            topic_code, survey, vintage,
        )
        return []


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


def geo_col_label(sumlevels: list[str]) -> str:
    """Human-readable label for the geography name column.

    Single sumlevel → plural display name (e.g. ``"Counties"``).
    Multiple distinct sumlevels, empty list, or unknown code → ``"Geography"``.
    """
    if not sumlevels or len(set(sumlevels)) != 1:
        return "Geography"
    try:
        from morpc_census.geos import SumLevel
        return SumLevel(sumlevels[0]).plural.title()
    except Exception:
        return "Geography"


def geo_col_from_geo_list(geo_list: list[dict] | None) -> str:
    """Derive the geography column label from a geo-list-store value."""
    if not geo_list:
        return "Geography"
    return geo_col_label(list(dict.fromkeys(g["sumlevel"] for g in geo_list)))
