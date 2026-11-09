"""The Playwright server lifts the redeem limit, so it must stay out of hosted use."""

import os
import subprocess
import sys
from pathlib import Path

import pytest

API_ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize(
    "hosted", [{"CONTAINER_APP_NAME": "talent-api"}, {"APP_ENV": "dev"}, {"APP_ENV": "uat"}, {"APP_ENV": "prod"}]
)
def test_refuses_to_start_in_a_hosted_environment(hosted):
    env = {k: v for k, v in os.environ.items() if k not in ("CONTAINER_APP_NAME", "APP_ENV")}
    result = subprocess.run(
        [sys.executable, "tests/e2e_server.py", "8199"],
        cwd=API_ROOT, env={**env, **hosted}, capture_output=True, text=True, timeout=30,
    )
    assert result.returncode != 0 and "hosted environment" in result.stderr


def test_application_code_never_loads_it():
    for path in (API_ROOT / "app").rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        assert "e2e_server" not in text and "redeem_rate_limiter.allow =" not in text, path
