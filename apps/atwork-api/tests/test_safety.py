import ast
import os
import subprocess
import sys
from pathlib import Path

from app.core.config import Settings

SERVICE_ROOT = Path(__file__).resolve().parents[1]
ALLOWED_THIRD_PARTY = {"app", "auth_client_py", "fastapi", "pydantic", "pydantic_settings"}


def test_refuses_to_start_outside_development_with_default_secrets():
    env = {k: v for k, v in os.environ.items() if k not in {"PLATFORM_JWT_SECRET", "INTERNAL_SERVICE_SECRET"}}
    env["APP_ENV"] = "production"
    result = subprocess.run([sys.executable, "-c", "import app.main"], cwd=SERVICE_ROOT, env=env, capture_output=True)
    assert result.returncode != 0


def test_only_imports_stdlib_shared_auth_and_its_own_code():
    for path in (SERVICE_ROOT / "app").rglob("*.py"):
        for node in ast.walk(ast.parse(path.read_text())):
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.level == 0:
                names = [node.module or ""]
            else:
                continue
            for name in names:
                top = name.split(".")[0]
                assert top in ALLOWED_THIRD_PARTY or top in sys.stdlib_module_names, f"{path}: {name}"


def test_has_no_setting_pointing_at_another_service_or_database():
    for field in Settings.model_fields:
        assert not field.endswith("_api_url"), field
        assert field != "database_url"
