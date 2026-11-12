"""Fail-closed validation of the shared trust anchors.

Every DijiOne backend ships insecure development defaults for
``PLATFORM_JWT_SECRET`` / ``INTERNAL_SERVICE_SECRET`` (and talent-api's
``EXTERNAL_SESSION_JWT_SECRET``) so local dev and CI work with no setup.
Those defaults must never reach a deployed non-development environment. A
service calls :func:`assert_trust_anchors_safe` once at startup; it raises
:class:`InsecureConfigError` (aborting the process) if ``APP_ENV`` is not a
development-class environment and a trust anchor is still unset, still the
known insecure default, or implausibly short.
"""

from __future__ import annotations

import logging
import warnings
from collections.abc import Mapping

logger = logging.getLogger("auth_client_py.security")

# The literal defaults shipped in every service's `app/core/config.py` and
# `.env.example`. Keep this list in sync if a default string changes.
INSECURE_DEFAULTS: frozenset[str] = frozenset(
    {
        "dev-only-insecure-secret-change-me",
        "dev-only-internal-secret-change-me",
        "dev-only-external-session-secret-change-me",
        "change-me",
        "",
    }
)

# APP_ENV values that are allowed to run with the insecure defaults.
DEV_ENVS: frozenset[str] = frozenset({"development", "dev-local", "local", "test", "ci"})

MIN_SECRET_LENGTH = 24


class InsecureConfigError(RuntimeError):
    """Raised at startup when a deployed environment still holds a dev secret."""


def assert_trust_anchors_safe(
    app_env: str,
    secrets: Mapping[str, str],
    *,
    min_length: int = MIN_SECRET_LENGTH,
    database_url: str | None = None,
) -> None:
    """Abort startup if a non-development environment holds an insecure secret.

    ``secrets`` maps a human name (e.g. ``"PLATFORM_JWT_SECRET"``) to its resolved
    value — each service passes the anchors it actually uses.

    In a development-class ``app_env`` this is a no-op, except that if the
    service is clearly running against a real database (``database_url`` is
    not SQLite) while still holding an insecure default, a warning is logged
    — a soft nudge that a hosted "dev" environment should still use real
    secrets.
    """
    env = (app_env or "").strip().lower()
    problems = [name for name, value in secrets.items() if _is_insecure(value, min_length)]

    if env in DEV_ENVS:
        if problems and database_url and not database_url.startswith("sqlite"):
            msg = (
                f"APP_ENV={app_env!r} but {', '.join(problems)} still hold the insecure "
                "development default while connected to a non-SQLite database. Set "
                "high-entropy values via the environment / Key Vault."
            )
            logger.warning(msg)
            warnings.warn(msg, stacklevel=2)
        return

    if problems:
        raise InsecureConfigError(
            f"Refusing to start with APP_ENV={app_env!r}: "
            + "; ".join(
                f"{name} is unset, still the insecure development default, or shorter "
                f"than {min_length} characters"
                for name in problems
            )
            + ". Set high-entropy values via the environment / Key Vault."
        )


def _is_insecure(value: str, min_length: int) -> bool:
    if value is None or value in INSECURE_DEFAULTS:
        return True
    return len(value) < min_length
