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
_DEFAULT_LATEST_VINTAGE = 2023

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
        return [{"label": str(y), "value": y} for y in range(2023, 2008, -1)]


@lru_cache(maxsize=1)
def scope_options() -> list[dict]:
    """All named scopes from morpc.SCOPES, sorted alphabetically."""
    try:
        from morpc_census.geos import SCOPES
        return [{"label": k, "value": k} for k in sorted(SCOPES.keys())]
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
            if desc.get("singular")
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
