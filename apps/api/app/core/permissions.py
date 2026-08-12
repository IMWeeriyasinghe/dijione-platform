"""Canonical DijiOne authorization catalog (Phase 2 CR §19-20, §29).

Single source of truth for every ``Role`` / ``Permission`` /
``RolePermission`` row the platform ships with. Both the Alembic migration
(one-time backfill) and ``scripts/seed.py`` (repeatable local reseed) import
this module so the two never drift.

Role/permission *keys* here are the same string values already stored in
``User.platform_role`` and ``UserModuleRole.role`` — this catalog adds a
resolvable permission bundle underneath those existing string columns; it
does not replace them (CLAUDE.md-extension §19: "Roles become permission
bundles").
"""

from __future__ import annotations

from dataclasses import dataclass

from app.core.constants import MODULE_TALENT_FLOW, PlatformRole, TalentFlowRole


@dataclass(frozen=True)
class PermissionDef:
    key: str
    name: str
    description: str
    module_key: str | None
    category: str


@dataclass(frozen=True)
class RoleDef:
    key: str
    name: str
    description: str
    module_key: str | None
    permissions: tuple[str, ...]


# --- Platform permissions (module_key=None) --------------------------------

PLATFORM_PERMISSIONS: list[PermissionDef] = [
    PermissionDef(
        "platform.admin.access", "Access Admin Center",
        "View the DijiOne Admin Center navigation and dashboard.", None, "Administration",
    ),
    PermissionDef(
        "platform.admin.manage_users", "Manage Users",
        "Activate/deactivate users, assign platform role (PLATFORM_USER/PLATFORM_ADMIN), "
        "manage module assignments and client scope.", None, "Administration",
    ),
    PermissionDef(
        "platform.admin.manage_admins", "Manage Administrators",
        "Grant or revoke SUPER_ADMIN / PLATFORM_ADMIN platform roles.", None, "Administration",
    ),
    PermissionDef(
        "platform.admin.manage_modules", "Manage Modules",
        "View and edit the DijiOne module registry.", None, "Administration",
    ),
    PermissionDef(
        "platform.admin.manage_roles", "Manage Roles & Permissions",
        "View role/permission catalog and edit non-system roles.", None, "Administration",
    ),
    PermissionDef(
        "platform.admin.manage_client_scopes", "Manage Client Access",
        "Assign client/portfolio scope to module assignments.", None, "Administration",
    ),
    PermissionDef(
        "platform.admin.view_audit", "View Audit Log",
        "Inspect platform administrative audit history.", None, "Administration",
    ),
]

PLATFORM_ROLES: list[RoleDef] = [
    RoleDef(
        PlatformRole.SUPER_ADMIN.value, "Super Admin",
        "Full platform administration, including managing other administrators.", None,
        tuple(p.key for p in PLATFORM_PERMISSIONS),
    ),
    RoleDef(
        PlatformRole.PLATFORM_ADMIN.value, "Platform Admin",
        "Manages ordinary users, module access, roles and client scope. "
        "Cannot manage other administrators.", None,
        (
            "platform.admin.access",
            "platform.admin.manage_users",
            "platform.admin.manage_modules",
            "platform.admin.manage_client_scopes",
            "platform.admin.view_audit",
        ),
    ),
    RoleDef(
        PlatformRole.PLATFORM_USER.value, "Platform User",
        "Standard authenticated DijiOne user with only assigned module access.", None, (),
    ),
]


# --- DijiTalentFlow permissions (module_key="talent-flow") -----------------

TALENT_PERMISSIONS: list[PermissionDef] = [
    PermissionDef(
        "talent.workspace.staff", "Staff Workspace Access",
        "Internal marker granting cross-client Talent Acquisition Workspace visibility "
        "(vs. the single-tenant Client Workspace).", MODULE_TALENT_FLOW, "Administration",
    ),
    PermissionDef(
        "talent.dashboard.read_own", "View Own Dashboard", "View the client dashboard for one's own organization.",
        MODULE_TALENT_FLOW, "Requests",
    ),
    PermissionDef(
        "talent.dashboard.read", "View Operations Dashboard", "View the cross-client TA operations dashboard.",
        MODULE_TALENT_FLOW, "Requests",
    ),
    PermissionDef(
        "talent.clients.read", "View Client Portfolios", "View the cross-client portfolio list.",
        MODULE_TALENT_FLOW, "Requests",
    ),
    PermissionDef(
        "talent.requests.read_own", "View Own Requests", "View talent requests for one's own organization.",
        MODULE_TALENT_FLOW, "Requests",
    ),
    PermissionDef(
        "talent.requests.read", "View All Requests", "View talent requests across authorized clients.",
        MODULE_TALENT_FLOW, "Requests",
    ),
    PermissionDef(
        "talent.requests.create", "Create Talent Request", "Submit a new talent request as a client.",
        MODULE_TALENT_FLOW, "Requests",
    ),
    PermissionDef(
        "talent.requests.update", "Update Request Stage/Status", "Update recruitment stage and TA status.",
        MODULE_TALENT_FLOW, "Requests",
    ),
    PermissionDef(
        "talent.requests.review", "Review Requests (Customer Success)",
        "Approve, reject or request clarification on a pending talent request.",
        MODULE_TALENT_FLOW, "Customer Success",
    ),
    PermissionDef(
        "talent.candidates.read_client_safe", "View Client-Safe Candidates",
        "View candidates approved for client visibility on one's own requests.",
        MODULE_TALENT_FLOW, "Candidates",
    ),
    PermissionDef(
        "talent.candidates.read", "View Candidate Pool", "View the full master candidate pool.",
        MODULE_TALENT_FLOW, "Candidates",
    ),
    PermissionDef(
        "talent.candidates.manage", "Manage Candidates", "Create/update candidate master records.",
        MODULE_TALENT_FLOW, "Candidates",
    ),
    PermissionDef(
        "talent.applications.read", "View Applications", "View candidate-to-request applications.",
        MODULE_TALENT_FLOW, "Applications",
    ),
    PermissionDef(
        "talent.applications.create", "Create Application", "Link a candidate to a talent request.",
        MODULE_TALENT_FLOW, "Applications",
    ),
    PermissionDef(
        "talent.applications.update", "Update Application", "Update application stage, status, score, visibility.",
        MODULE_TALENT_FLOW, "Applications",
    ),
    PermissionDef(
        "talent.interviews.read_own", "View Own Interviews", "View interviews for one's own organization.",
        MODULE_TALENT_FLOW, "Interviews",
    ),
    PermissionDef(
        "talent.interviews.read", "View Interviews", "View the cross-client interview manager.",
        MODULE_TALENT_FLOW, "Interviews",
    ),
    PermissionDef(
        "talent.interviews.manage", "Manage Interviews", "Schedule and update interview status.",
        MODULE_TALENT_FLOW, "Interviews",
    ),
    PermissionDef(
        "talent.messages.read_own", "View Own Messages", "View messages on one's own requests.",
        MODULE_TALENT_FLOW, "Messages",
    ),
    PermissionDef(
        "talent.messages.read", "View Messages", "View messages across authorized requests.",
        MODULE_TALENT_FLOW, "Messages",
    ),
    PermissionDef(
        "talent.messages.create", "Send Message", "Send a message on a talent request.",
        MODULE_TALENT_FLOW, "Messages",
    ),
    PermissionDef(
        "talent.documents.read_own", "View Own Documents", "View documents on one's own requests.",
        MODULE_TALENT_FLOW, "Documents",
    ),
    PermissionDef(
        "talent.documents.read", "View Documents", "View documents across authorized requests.",
        MODULE_TALENT_FLOW, "Documents",
    ),
    PermissionDef(
        "talent.documents.create", "Upload Document", "Upload a document to a talent request.",
        MODULE_TALENT_FLOW, "Documents",
    ),
]

_TA_MEMBER_PERMISSIONS = (
    "talent.workspace.staff",
    "talent.dashboard.read",
    "talent.clients.read",
    "talent.requests.read",
    "talent.requests.update",
    "talent.candidates.read",
    "talent.candidates.manage",
    "talent.applications.read",
    "talent.applications.create",
    "talent.applications.update",
    "talent.interviews.read",
    "talent.interviews.manage",
    "talent.messages.read",
    "talent.messages.create",
    "talent.documents.read",
    "talent.documents.create",
)

TALENT_ROLES: list[RoleDef] = [
    RoleDef(
        TalentFlowRole.TALENT_CLIENT.value, "Talent Client",
        "External client user scoped to their own organization's requests.", MODULE_TALENT_FLOW,
        (
            "talent.dashboard.read_own",
            "talent.requests.read_own",
            "talent.requests.create",
            "talent.candidates.read_client_safe",
            "talent.interviews.read_own",
            "talent.messages.read_own",
            "talent.messages.create",
            "talent.documents.read_own",
            "talent.documents.create",
        ),
    ),
    RoleDef(
        TalentFlowRole.TA_MEMBER.value, "Talent Acquisition Member",
        "Talent Acquisition staff with cross-client operational access.", MODULE_TALENT_FLOW,
        _TA_MEMBER_PERMISSIONS,
    ),
    RoleDef(
        TalentFlowRole.CUSTOMER_SUCCESS.value, "Customer Success",
        "Reviews and approves incoming talent requests in addition to standard staff access.",
        MODULE_TALENT_FLOW,
        _TA_MEMBER_PERMISSIONS + ("talent.requests.review",),
    ),
    RoleDef(
        TalentFlowRole.TA_MANAGER.value, "TA Manager",
        "TA Member permissions plus Customer Success review rights and cross-client oversight.",
        MODULE_TALENT_FLOW,
        _TA_MEMBER_PERMISSIONS + ("talent.requests.review",),
    ),
]

ALL_PERMISSIONS: list[PermissionDef] = PLATFORM_PERMISSIONS + TALENT_PERMISSIONS
ALL_ROLES: list[RoleDef] = PLATFORM_ROLES + TALENT_ROLES
