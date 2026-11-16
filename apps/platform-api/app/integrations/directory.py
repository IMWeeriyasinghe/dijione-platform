"""The Microsoft Entra directory, read through Microsoft Graph. READ ONLY.

DijiOne reads employee identities (search, profile, photo, group memberships) from the directory
with the platform-api Container App's own managed identity, holding read-only Graph application
permissions (User.Read.All, GroupMember.Read.All). No client secret, no write call: this module
issues GET requests only, and a test asserts it never sends anything else.

``DIRECTORY_MODE=mock`` (the default, used locally and in CI) serves an in-memory directory.
"""

from __future__ import annotations

import logging
import re
import threading
from dataclasses import dataclass, field
from typing import Protocol

import httpx

from app.core.config import get_settings

logger = logging.getLogger(__name__)

GRAPH = "https://graph.microsoft.com/v1.0"
_SCOPE = "https://graph.microsoft.com/.default"
_USER_FIELDS = "id,displayName,mail,userPrincipalName,jobTitle,department,employeeId,accountEnabled,userType"
SEARCH_LIMIT = 15
GROUP_LIMIT = 200


class DirectoryUnavailable(Exception):
    """The directory could not be read (not configured, permission missing, Graph error)."""


@dataclass(frozen=True)
class DirectoryUser:
    object_id: str
    display_name: str
    email: str
    user_principal_name: str
    job_title: str | None = None
    department: str | None = None
    employee_id: str | None = None
    account_enabled: bool = True
    user_type: str = "Member"


@dataclass(frozen=True)
class DirectoryGroup:
    object_id: str
    display_name: str
    group_type: str
    direct: bool


@dataclass(frozen=True)
class Photo:
    content: bytes
    content_type: str


class DirectoryProvider(Protocol):
    def search(self, query: str, limit: int = SEARCH_LIMIT) -> list[DirectoryUser]: ...
    def get(self, object_id: str) -> DirectoryUser | None: ...
    def find_by_email(self, email: str) -> list[DirectoryUser]: ...
    def photo(self, object_id: str) -> Photo | None: ...
    def groups(self, object_id: str) -> list[DirectoryGroup]: ...


def internal_domains() -> set[str]:
    return {d.strip().lower() for d in get_settings().entra_internal_email_domains.split(",") if d.strip()}


def is_internal_member(user: DirectoryUser, domains: set[str] | None = None) -> bool:
    """An enabled member (not a guest) of our tenant with an address on an internal domain."""
    domains = internal_domains() if domains is None else domains
    email = (user.email or "").lower()
    upn = (user.user_principal_name or "").lower()
    return bool(
        user.account_enabled
        and user.user_type == "Member"
        and "#ext#" not in upn
        and "#ext#" not in email
        and "@" in email
        and email.rsplit("@", 1)[1] in domains
    )


def group_type(group: dict) -> str:
    if "Unified" in (group.get("groupTypes") or []):
        return "Microsoft 365"
    if group.get("securityEnabled") and group.get("mailEnabled"):
        return "Mail-enabled security"
    if group.get("securityEnabled"):
        return "Security"
    return "Distribution"


def _user(raw: dict) -> DirectoryUser:
    upn = raw.get("userPrincipalName") or ""
    return DirectoryUser(
        object_id=raw["id"],
        display_name=raw.get("displayName") or upn,
        email=(raw.get("mail") or upn).lower(),
        user_principal_name=upn,
        job_title=raw.get("jobTitle"),
        department=raw.get("department"),
        employee_id=(raw.get("employeeId") or None),
        account_enabled=bool(raw.get("accountEnabled", True)),
        user_type=raw.get("userType") or "Member",
    )


_SAFE_QUERY = re.compile(r"[^\w@.\-' ]+", re.UNICODE)


def clean_query(query: str) -> str:
    """Characters allowed in a directory search; everything else is dropped (no OData injection)."""
    return _SAFE_QUERY.sub("", query or "").strip()[:64]


class GraphDirectoryProvider:
    """Microsoft Graph with the Container App's managed identity. GET requests only."""

    def __init__(self, *, credential=None, client: httpx.Client | None = None, timeout: float = 5.0) -> None:
        self._credential = credential
        self._client = client
        self._timeout = timeout

    def _token(self) -> str:
        if self._credential is None:
            from azure.identity import DefaultAzureCredential

            self._credential = DefaultAzureCredential()
        try:
            return self._credential.get_token(_SCOPE).token
        except Exception as exc:  # credential chain failures carry no secrets
            raise DirectoryUnavailable("The directory identity could not obtain a token") from exc

    def _get(self, url: str, *, params: dict | None = None, eventual: bool = False) -> httpx.Response:
        headers = {"Authorization": f"Bearer {self._token()}"}
        if eventual:
            headers["ConsistencyLevel"] = "eventual"
        try:
            if self._client is not None:
                resp = self._client.get(url, params=params, headers=headers)
            else:
                resp = httpx.get(url, params=params, headers=headers, timeout=self._timeout)
        except httpx.HTTPError as exc:
            raise DirectoryUnavailable("The directory could not be reached") from exc
        if resp.status_code in (401, 403):
            logger.warning("Graph refused a directory read: %s", resp.status_code)
            raise DirectoryUnavailable("The directory refused the request (permission missing?)")
        if resp.status_code >= 500 or resp.status_code == 429:
            raise DirectoryUnavailable(f"The directory answered {resp.status_code}")
        return resp

    def search(self, query: str, limit: int = SEARCH_LIMIT) -> list[DirectoryUser]:
        q = clean_query(query)
        if len(q) < 2:
            return []
        base = "accountEnabled eq true and userType eq 'Member'"
        params = {"$select": _USER_FIELDS, "$top": str(min(limit, SEARCH_LIMIT)), "$count": "true"}
        if q.isdigit():
            params["$filter"] = f"employeeId eq '{q}' and {base}"
        else:
            term = q.replace('"', "")
            params["$search"] = f'"displayName:{term}" OR "mail:{term}" OR "userPrincipalName:{term}"'
            params["$filter"] = base
        resp = self._get(f"{GRAPH}/users", params=params, eventual=True)
        if resp.status_code != 200:
            raise DirectoryUnavailable(f"The directory search answered {resp.status_code}")
        domains = internal_domains()
        users = [_user(raw) for raw in resp.json().get("value", [])]
        return [u for u in users if is_internal_member(u, domains)][:limit]

    def get(self, object_id: str) -> DirectoryUser | None:
        if not re.fullmatch(r"[0-9a-fA-F-]{36}", object_id or ""):
            return None
        resp = self._get(f"{GRAPH}/users/{object_id}", params={"$select": _USER_FIELDS})
        if resp.status_code == 404:
            return None
        if resp.status_code != 200:
            raise DirectoryUnavailable(f"The directory answered {resp.status_code}")
        return _user(resp.json())

    def find_by_email(self, email: str) -> list[DirectoryUser]:
        address = (email or "").strip().lower().replace("'", "''")
        if "@" not in address:
            return []
        params = {
            "$select": _USER_FIELDS,
            "$filter": f"mail eq '{address}' or userPrincipalName eq '{address}' or otherMails/any(m:m eq '{address}')",
            "$count": "true",
            "$top": "5",
        }
        resp = self._get(f"{GRAPH}/users", params=params, eventual=True)
        if resp.status_code != 200:
            raise DirectoryUnavailable(f"The directory answered {resp.status_code}")
        return [_user(raw) for raw in resp.json().get("value", [])]

    def photo(self, object_id: str) -> Photo | None:
        if not re.fullmatch(r"[0-9a-fA-F-]{36}", object_id or ""):
            return None
        resp = self._get(f"{GRAPH}/users/{object_id}/photos/96x96/$value")
        if resp.status_code == 404:
            return None
        if resp.status_code != 200:
            raise DirectoryUnavailable(f"The directory photo answered {resp.status_code}")
        return Photo(content=resp.content, content_type=resp.headers.get("content-type", "image/jpeg").split(";")[0])

    def groups(self, object_id: str) -> list[DirectoryGroup]:
        if not re.fullmatch(r"[0-9a-fA-F-]{36}", object_id or ""):
            return []
        fields = {"$select": "id,displayName,groupTypes,securityEnabled,mailEnabled", "$top": "100"}
        found: list[dict] = []
        url: str | None = f"{GRAPH}/users/{object_id}/transitiveMemberOf/microsoft.graph.group"
        params: dict | None = fields
        while url and len(found) < GROUP_LIMIT:
            resp = self._get(url, params=params)
            if resp.status_code == 404:
                return []
            if resp.status_code != 200:
                raise DirectoryUnavailable(f"The directory answered {resp.status_code}")
            body = resp.json()
            found.extend(body.get("value", []))
            url, params = body.get("@odata.nextLink"), None
        direct: set[str] = set()
        url, params = f"{GRAPH}/users/{object_id}/memberOf/microsoft.graph.group", {"$select": "id", "$top": "100"}
        while url and len(direct) < GROUP_LIMIT:
            resp = self._get(url, params=params)
            if resp.status_code != 200:
                break
            body = resp.json()
            direct.update(g["id"] for g in body.get("value", []))
            url, params = body.get("@odata.nextLink"), None
        out = [
            DirectoryGroup(
                object_id=g["id"], display_name=g.get("displayName") or g["id"], group_type=group_type(g),
                direct=g["id"] in direct,
            )
            for g in found[:GROUP_LIMIT]
        ]
        return sorted(out, key=lambda g: (not g.direct, g.display_name.lower()))


@dataclass
class MockDirectoryProvider:
    """In-memory directory for local development and tests."""

    users: list[DirectoryUser] = field(default_factory=list)
    photos: dict[str, Photo] = field(default_factory=dict)
    memberships: dict[str, list[DirectoryGroup]] = field(default_factory=dict)
    unavailable: bool = False

    def _check(self) -> None:
        if self.unavailable:
            raise DirectoryUnavailable("The directory could not be reached")

    def search(self, query: str, limit: int = SEARCH_LIMIT) -> list[DirectoryUser]:
        self._check()
        q = clean_query(query).lower()
        if len(q) < 2:
            return []
        domains = internal_domains()
        hits = [
            u for u in self.users
            if is_internal_member(u, domains)
            and (
                q in u.display_name.lower() or q in u.email.lower() or q in u.user_principal_name.lower()
                or (u.employee_id or "") == q
            )
        ]
        return hits[: min(limit, SEARCH_LIMIT)]

    def get(self, object_id: str) -> DirectoryUser | None:
        self._check()
        return next((u for u in self.users if u.object_id == object_id), None)

    def find_by_email(self, email: str) -> list[DirectoryUser]:
        self._check()
        address = (email or "").strip().lower()
        return [u for u in self.users if address in (u.email.lower(), u.user_principal_name.lower())]

    def photo(self, object_id: str) -> Photo | None:
        self._check()
        return self.photos.get(object_id)

    def groups(self, object_id: str) -> list[DirectoryGroup]:
        self._check()
        return list(self.memberships.get(object_id, []))


_provider: DirectoryProvider | None = None
_lock = threading.Lock()


def get_directory_provider() -> DirectoryProvider:
    global _provider
    with _lock:
        if _provider is None:
            _provider = GraphDirectoryProvider() if get_settings().directory_mode == "graph" else MockDirectoryProvider()
        return _provider


def set_directory_provider(provider: DirectoryProvider | None) -> None:
    """Tests (and local development) install a provider; None restores the configured one."""
    global _provider
    with _lock:
        _provider = provider
