"""Canonical DijiOne authorization catalog (Phase 2 CR §19-20, §29).

Single source of truth for every ``Role`` / ``Permission`` / ``RolePermission``
row Platform Core ships with. Both the Alembic migration (one-time backfill)
and ``scripts/seed.py`` (repeatable local reseed) import this module so the
two never drift.

Role/permission *keys* here are plain strings, including the DijiTalentFlow
role keys ("TALENT_CLIENT", "TA_MEMBER", …) — Platform Core owns the Role/
Permission catalog tables (every module's roles are registered into it), but
must not import talent-api's ``TalentFlowRole`` enum across the service
boundary (CR §11), so those role keys are inlined as literals here. talent-api
keeps its own copy of the same literal set in
``apps/talent-api/app/core/constants.py`` for type-safe internal use; the
seed values must be kept in sync by convention (documented in
``docs/platform/service-contracts.md``), the same "hand-kept-in-sync" pattern
already used for the frontend/backend enum mirrors.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.core.constants import MODULE_BIRTHDAY, MODULE_TALENT_FLOW, PlatformRole


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
# Platform Core stores these rows so it can resolve talent-flow permissions
# into signed JWT claims at login (Phase 2.5) — it does not implement or
# depend on any talent-flow business logic (CR §6.2).

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
        "TALENT_CLIENT", "Talent Client",
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
        "TA_MEMBER", "Talent Acquisition Member",
        "Talent Acquisition staff with cross-client operational access.", MODULE_TALENT_FLOW,
        _TA_MEMBER_PERMISSIONS,
    ),
    RoleDef(
        "CUSTOMER_SUCCESS", "Customer Success",
        "Reviews and approves incoming talent requests in addition to standard staff access.",
        MODULE_TALENT_FLOW,
        _TA_MEMBER_PERMISSIONS + ("talent.requests.review",),
    ),
    RoleDef(
        "TA_MANAGER", "TA Manager",
        "TA Member permissions plus Customer Success review rights and cross-client oversight.",
        MODULE_TALENT_FLOW,
        _TA_MEMBER_PERMISSIONS + ("talent.requests.review",),
    ),
]


# --- DijiBirthday permissions (module_key="birthday") ----------------------
# Platform Core stores these rows so it can resolve birthday permissions
# into signed JWT claims at login — it does not implement or depend on any
# birthday-api business logic.

BIRTHDAY_PERMISSIONS: list[PermissionDef] = [
    PermissionDef(
        "birthday.dashboard.read", "View Dashboard", "View the DijiBirthday dashboard.",
        MODULE_BIRTHDAY, "Dashboard",
    ),
    PermissionDef(
        "birthday.orders.read", "View Cake Orders", "View the cake orders register and order detail.",
        MODULE_BIRTHDAY, "Orders",
    ),
    PermissionDef(
        "birthday.orders.create", "Create Manual Order", "Manually create a birthday cake order.",
        MODULE_BIRTHDAY, "Orders",
    ),
    PermissionDef(
        "birthday.orders.update", "Edit Order", "Edit an existing birthday cake order.",
        MODULE_BIRTHDAY, "Orders",
    ),
    PermissionDef(
        "birthday.orders.hold_release", "Hold/Release Orders", "Place an order on hold or release it.",
        MODULE_BIRTHDAY, "Orders",
    ),
    PermissionDef(
        "birthday.orders.cancel", "Cancel Order", "Cancel a birthday cake order.",
        MODULE_BIRTHDAY, "Orders",
    ),
    PermissionDef(
        "birthday.orders.send_supplier", "Send Order to Supplier", "Send/resend an order to its supplier.",
        MODULE_BIRTHDAY, "Orders",
    ),
    PermissionDef(
        "birthday.orders.verify", "Verify Delivery Address",
        "Mark a delivery address VERIFIED — the one routine checkpoint that "
        "auto-releases a standard order to its supplier.",
        MODULE_BIRTHDAY, "Orders",
    ),
    PermissionDef(
        "birthday.orders.review", "Confirm & Release Flagged Orders",
        "One-click release for an order flagged into REQUIRES_REVIEW.",
        MODULE_BIRTHDAY, "Orders",
    ),
    PermissionDef(
        "birthday.orders.delete", "Delete Draft Orders", "Hard-delete a never-actioned DRAFT order.",
        MODULE_BIRTHDAY, "Orders",
    ),
    PermissionDef(
        "birthday.suppliers.read", "View Suppliers", "View the supplier directory.",
        MODULE_BIRTHDAY, "Suppliers",
    ),
    PermissionDef(
        "birthday.suppliers.manage", "Manage Suppliers", "Create/update suppliers, locations and catalogue.",
        MODULE_BIRTHDAY, "Suppliers",
    ),
    PermissionDef(
        "birthday.config.manage", "Manage Detection Configuration", "Edit birthday detection thresholds/window.",
        MODULE_BIRTHDAY, "Administration",
    ),
    PermissionDef(
        "birthday.portal.access", "Supplier Portal Access", "Access the supplier portal.",
        MODULE_BIRTHDAY, "Supplier Portal",
    ),
    PermissionDef(
        "birthday.portal.respond", "Respond to Orders (Supplier)", "Confirm/request change/reject an order.",
        MODULE_BIRTHDAY, "Supplier Portal",
    ),
]

BIRTHDAY_ROLES: list[RoleDef] = [
    RoleDef(
        "BIRTHDAY_USER", "HR/Birthday User", "View dashboard, upcoming birthdays, and orders.", MODULE_BIRTHDAY,
        ("birthday.dashboard.read", "birthday.orders.read", "birthday.suppliers.read"),
    ),
    RoleDef(
        "BIRTHDAY_ADMIN", "HR/Birthday Admin", "Full order/supplier/config management.", MODULE_BIRTHDAY,
        tuple(
            p.key for p in BIRTHDAY_PERMISSIONS
            if p.key not in ("birthday.portal.access", "birthday.portal.respond")
        ),
    ),
    RoleDef(
        "BIRTHDAY_SUPPLIER", "Birthday Supplier", "Isolated supplier-portal-only role.", MODULE_BIRTHDAY,
        ("birthday.portal.access", "birthday.portal.respond"),
    ),
]

ALL_PERMISSIONS: list[PermissionDef] = PLATFORM_PERMISSIONS + TALENT_PERMISSIONS + BIRTHDAY_PERMISSIONS
ALL_ROLES: list[RoleDef] = PLATFORM_ROLES + TALENT_ROLES + BIRTHDAY_ROLES
