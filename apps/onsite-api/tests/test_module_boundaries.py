"""Module-independence guards (docs/onsite/architecture.md rules 2, 3, 6).

1. Azure SQL access (pyodbc, the onsite.* schema, the SQL token attribute)
   appears ONLY under app/attendance_source/.
2. No first-party import other than this service's own ``app`` package and
   the shared ``auth_client_py`` contract package.
3. No external application URL settings other than PLATFORM_API_URL and
   PEOPLE_API_URL; no database URL other than this service's own.
4. Every attendance repository read requires ``allowed_site_ids``.
"""

import ast
import inspect
import re
import sys
from pathlib import Path

APP = Path(__file__).resolve().parents[1] / "app"
SOURCE_PKG = APP / "attendance_source"

_SQL_PATTERNS = [
    re.compile(r"\bpyodbc\b"),
    re.compile(r"\bonsite\.(Sites|AttendanceEvents|AgentStatus|Batches)\b"),
    re.compile(r"SQL_COPT_SS_ACCESS_TOKEN"),
    re.compile(r"database\.windows\.net"),
    re.compile(r"ODBC Driver"),
]


def _py_files():
    return [p for p in APP.rglob("*.py") if "__pycache__" not in p.parts]


def test_azure_sql_access_only_in_attendance_source():
    offenders = []
    for path in _py_files():
        if SOURCE_PKG in path.parents:
            continue
        text = path.read_text(encoding="utf-8")
        offenders += [f"{path.relative_to(APP)}: {p.pattern}" for p in _SQL_PATTERNS if p.search(text)]
    assert offenders == []


def test_attendance_source_never_reads_batches_or_api_key_hash():
    queries = (SOURCE_PKG / "queries.py").read_text(encoding="utf-8").split('"""', 2)[2]
    assert "ApiKeyHash" not in queries and "Batches" not in queries
    assert not re.search(r"\b(INSERT|UPDATE|DELETE|MERGE|ALTER|CREATE|DROP|TRUNCATE|EXEC)\b", queries, re.I)


_THIRD_PARTY = {
    "fastapi", "starlette", "pydantic", "pydantic_settings", "sqlalchemy", "alembic", "httpx",
    "pyodbc", "azure", "jose", "uvicorn",
}
_FIRST_PARTY_ALLOWED = {"app", "auth_client_py"}


def test_no_first_party_imports_beyond_shared_contracts():
    stdlib = set(sys.stdlib_module_names)
    offenders = []
    for path in _py_files():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            names = []
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                names = [node.module]
            for name in names:
                top = name.split(".")[0]
                if top not in stdlib and top not in _THIRD_PARTY and top not in _FIRST_PARTY_ALLOWED:
                    offenders.append(f"{path.relative_to(APP)}: {name}")
    assert offenders == []


def test_only_platform_and_people_urls_and_own_database():
    from app.core.config import Settings

    fields = set(Settings.model_fields)
    url_fields = {f for f in fields if f.endswith("_url")}
    assert url_fields == {"database_url", "platform_api_url", "people_api_url"}
    for forbidden in ("birthday", "talent", "admin_api", "recruitment", "commercial", "spark"):
        assert not any(forbidden in f for f in fields), forbidden
    text = "".join(p.read_text(encoding="utf-8") for p in _py_files())
    for other_db in ("people.db", "birthday.db", "talent.db", "platform.db", "recruitment.db",
                     "people_dev", "birthday_dev", "talent_dev", "platform_dev", "recruitment_dev"):
        assert other_db not in text, other_db
    for other_url in ("BIRTHDAY_API_URL", "TALENT_API_URL", "ADMIN_API_URL", "RECRUITMENT_API_URL",
                      "/api/birthday", "/api/talent", "/api/admin/", "/api/recruitment"):
        assert other_url not in text, other_url


def test_repository_reads_require_allowed_site_ids():
    from app.repositories.attendance_repository import AttendanceRepository

    methods = [m for name, m in inspect.getmembers(AttendanceRepository, inspect.isfunction) if not name.startswith("_")]
    assert methods
    for m in methods:
        param = inspect.signature(m).parameters.get("allowed_site_ids")
        assert param is not None, m.__name__
        assert param.kind is inspect.Parameter.KEYWORD_ONLY and param.default is inspect.Parameter.empty, m.__name__
