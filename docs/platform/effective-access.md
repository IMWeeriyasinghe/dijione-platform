# DijiOne Effective Access Resolution (Phase 2.6)

This document is the precise specification of how DijiOne computes a user's
**effective** access to a module once Access Groups exist alongside direct
assignment. It exists because getting this rule exactly right — and keeping
it in exactly one place — is the load-bearing part of Phase 2.6. The
implementation is `AuthorizationService.effective_module_roles` /
`effective_client_scope` / `effective_permissions`
(`apps/platform-api/app/services/authorization_service.py`); see
`docs/platform/access-groups.md` for the group model itself and
`docs/platform/authorization.md` for how this fits into the rest of the
authorization engine.

## The rule (additive ALLOW, no DENY)

For a given user and `module_key`, a **contributing assignment** is either:

- the user's own `UserModuleRole` for that module, where `enabled=True`; or
- a `GroupModuleRole` for that module, where `enabled=True`, belonging to
  an `AccessGroup` the user is an active member of
  (`AccessGroup.status == ACTIVE`).

Everything else contributes nothing: a disabled direct assignment, a
disabled `GroupModuleRole`, or any assignment (direct or group) belonging to
an inactive group, is excluded before the rules below are applied. There is
no DENY semantics anywhere in this phase — a contributing assignment can
only add access, never subtract access granted by another contributing
assignment.

1. **Effective role(s)** = the set of distinct `role` values across every
   contributing assignment. A user can effectively hold more than one role
   for the same module if their direct role differs from a group's role.
2. **Effective permissions** = the union of the permission set for every
   distinct role in (1). A permission present via any contributing role is
   in the effective set, regardless of how many roles grant it.
3. **Effective client scope**:
   - If **any** contributing assignment is unrestricted — `all_clients=True`
     on one of its scope rows, **or it has no scope rows at all** (the same
     pre-Phase-2 back-compat default `client_scope_for` already applies to
     a bare direct assignment) — the effective scope is **ALL_CLIENTS**
     (`None`), full stop. This overrides every other contributing
     assignment's scope, no matter how restrictive.
   - Otherwise, the effective scope is the **union** of every contributing
     assignment's concrete `client_id`s.

This is implemented as three separate methods rather than one combined
structure because each answers a different question a caller needs
independently (`effective_module_roles` for "what roles", `effective_client_scope`
for "which clients", `effective_permissions` for "what actions") — but all
three walk the same contributing-assignment set, so they can never disagree
with each other about who contributes.

## Worked examples

All examples are for one user, one module (`talent-flow`), unless noted.

### 1. Direct only

- Direct: `UserModuleRole(role=TA_MEMBER, enabled=True)`, scope: two rows,
  `client_ids=[1, 2]`, `all_clients=False`.
- No group memberships.

Result: effective role = `{TA_MEMBER}`; effective permissions = TA_MEMBER's
permission set; effective client scope = `[1, 2]`. Identical to Phase 2
behavior — a user with no group memberships sees no change from Phase 2.6.

### 2. Group only

- No direct `UserModuleRole` for this module.
- Member of active group "TA Team", which has
  `GroupModuleRole(module_key=talent-flow, role=TA_MEMBER, enabled=True)`
  with `all_clients=True`.

Result: effective role = `{TA_MEMBER}`, source `GROUP` ("TA Team");
effective client scope = ALL_CLIENTS (`None`). This user has never been
individually assigned to DijiTalentFlow — their access comes entirely from
group membership, and would disappear entirely if they left the group.

### 3. Direct + group combined

- Direct: `UserModuleRole(role=TA_MEMBER, enabled=True)`, scope
  `client_ids=[1, 2]`.
- Also a member of active group "Customer Success Pod", which has
  `GroupModuleRole(module_key=talent-flow, role=CUSTOMER_SUCCESS, enabled=True)`
  with scope `client_ids=[3]`.

Result: effective role = `{TA_MEMBER, CUSTOMER_SUCCESS}` (both, from
different sources); effective permissions = union of both roles'
permissions, which in practice means this user gets `talent.requests.review`
(CUSTOMER_SUCCESS-only) on top of everything TA_MEMBER already grants;
effective client scope = `{1, 2} ∪ {3}` = `[1, 2, 3]` — neither
contributing assignment alone covered client 3, but the union does.
`sources` for `talent.requests.review` shows `GROUP` ("Customer Success
Pod"); sources for a TA_MEMBER-only permission show `DIRECT`.

### 4. ALL_CLIENTS override

- Direct: `UserModuleRole(role=TA_MEMBER)`, scope `client_ids=[1]`
  (restricted to one client).
- Group "TA Team" grants `GroupModuleRole(role=TA_MEMBER, all_clients=True)`.

Result: effective client scope = ALL_CLIENTS (`None`), even though the
user's own direct assignment was deliberately restricted to client 1. The
group's unrestricted grant wins — this is the override rule from step 3
above, and it is the one rule in this document most worth double-checking
before relying on a restrictive direct assignment to actually restrict
someone who might also be in an unrestricted group.

### 5. Inactive group contributes nothing

- Direct: none.
- Member of group "Legacy Ops", which has a `GroupModuleRole` granting
  `TA_MEMBER`, but `AccessGroup.status == INACTIVE`.

Result: effective role = `{}` (empty); no access to the module at all. The
membership row still exists — deactivating the group is enough to remove
its effect from every member without touching membership rows or the
group's own module-role rows.

### 6. Disabled group assignment contributes nothing

- Member of active group "TA Team", which has
  `GroupModuleRole(role=TA_MEMBER, enabled=False)` — the assignment itself
  was disabled without deactivating the whole group or removing the member.

Result: this particular grant contributes nothing (same treatment as a
disabled direct `UserModuleRole`), even though the group is active and the
user is an active member of it. If the user has no other contributing
assignment, effective role for this module is empty.

## Explainability: the `sources` field

Every method that walks contributing assignments tags each one with its
provenance via the internal `ResolvedGrant` dataclass:
`source_type: "DIRECT" | "GROUP"`, plus `source_name` (the group's
`display_name`, when group-derived). This isn't a separate "explain this
access" computation built after the fact — it's produced by the same walk
that computes the effective values, so it can never drift from what was
actually granted.

The Admin Center's Effective Access API
(`GET /api/admin/users/{id}/effective-access`) exposes this as
`sources: list[AccessSourceOut]` on each module's
`EffectiveModuleAccessOut`. The Effective Access tab on the User Detail page
renders each contributing role as a `DIRECT` badge or an
`INHERITED FROM <Group Name>` badge, so "why does this user have this
access?" is answered by the same screen that shows *that* they have it —
see `docs/platform/admin-center.md` "Effective Access view".

## Claims staleness (unchanged trade-off)

Group-derived access flows into the signed JWT exactly the same way direct
access already did in Phase 2/2.5: `claims_service.build_claims` calls the
`effective_*` methods above and embeds the result in `module_roles` at
**login time**. Adding a user to a group, removing them, or changing a
group's module assignment does not retroactively update a token already in
a browser — it takes effect the next time that user's token is reissued
(next login, or a future refresh flow), bounded by `jwt_expires_minutes`.

This is not a new trade-off introduced by groups — it is the identical,
already-documented staleness window direct `UserModuleRole` changes have had
since Phase 2.5's claims-based model
(`docs/platform/failure-isolation.md` "Auth: signed claims, not a live
dependency"). Phase 2.6 does not add a claims-refresh or revocation
mechanism; a lightweight one remains a candidate future improvement if the
token-TTL window proves too coarse in practice (see
`docs/mvp-status.md` "Next autonomous phase").
