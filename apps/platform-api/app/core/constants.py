"""Platform-level enumerations (Platform Core's owned constants only).

Business-domain enums (talent-flow stages/statuses, integration providers,
notification types, …) live in the service that owns that business data
(``apps/talent-api/app/core/constants.py``) — Platform Core only needs to
know platform roles and the module registry's key vocabulary. See
``docs/platform/service-architecture.md``.
"""

from enum import StrEnum


class PlatformRole(StrEnum):
    PLATFORM_USER = "PLATFORM_USER"
    PLATFORM_ADMIN = "PLATFORM_ADMIN"
    SUPER_ADMIN = "SUPER_ADMIN"


MODULE_TALENT_FLOW = "talent-flow"
MODULE_BIRTHDAY = "birthday"
MODULE_SPARK = "spark"
