"""Helpers for interpreting Therapeutic Zone Lighting state."""


def tzl_zone_is_on(zone: dict) -> bool:
    """Return whether a TZL zone emits light.

    The API rejects ``state=OFF`` as a command for an individual zone, but
    responses can still report ``state=OFF``.  A successful per-zone off
    command can also leave the mode at ``NORMAL`` and set intensity to zero.
    Treat either representation as off.
    """
    state = zone.get("state", "OFF")
    if state in {"OFF", "DISABLED"}:
        return False

    intensity = zone.get("intensity")
    if intensity is not None:
        try:
            return int(intensity) > 0
        except (TypeError, ValueError):
            pass

    return True


def tzl_zone_is_off(zone: dict) -> bool:
    """Return whether a TZL zone is switched off."""
    return not tzl_zone_is_on(zone)
