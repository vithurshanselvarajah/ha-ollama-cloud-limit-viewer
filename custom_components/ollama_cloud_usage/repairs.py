from __future__ import annotations

from homeassistant.core import HomeAssistant
from homeassistant.helpers import issue_registry as ir

from .const import DOMAIN

ISSUE_TEAM_SCOPE_UNAVAILABLE = "team_scope_unavailable"


def async_create_team_scope_issue(
    hass: HomeAssistant, entry_id: str, account_name: str
) -> None:
    """Raise an issue when team scope was requested but is not available."""
    ir.async_create_issue(
        hass,
        DOMAIN,
        f"{ISSUE_TEAM_SCOPE_UNAVAILABLE}_{entry_id}",
        is_fixable=False,
        severity=ir.IssueSeverity.WARNING,
        translation_key=ISSUE_TEAM_SCOPE_UNAVAILABLE,
        translation_placeholders={"account_name": account_name},
    )


def async_delete_team_scope_issue(hass: HomeAssistant, entry_id: str) -> None:
    """Remove the issue once team scope works."""
    ir.async_delete_issue(hass, DOMAIN, f"{ISSUE_TEAM_SCOPE_UNAVAILABLE}_{entry_id}")
