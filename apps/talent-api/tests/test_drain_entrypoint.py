"""The drain job's entry point resolves the way the container starts it.

Each check runs in a separate interpreter from the app directory (the image's
working directory) and imports the module without calling main(), so no drain runs.
"""

import subprocess
import sys
from pathlib import Path

APP_DIR = Path(__file__).resolve().parents[1]


def _run(code):
    return subprocess.run([sys.executable, "-c", code], cwd=APP_DIR, capture_output=True, text=True, timeout=120)


def test_module_form_used_by_the_job_resolves():
    # `python -m scripts.drain_audit_outbox` puts the working directory first on sys.path.
    result = _run("import sys; sys.path.insert(0, ''); import scripts.drain_audit_outbox as m; assert callable(m.main)")
    assert result.returncode == 0, result.stderr


def test_file_form_resolves():
    # `python scripts/drain_audit_outbox.py` puts scripts/ first on sys.path instead.
    result = _run(
        "import runpy, sys; sys.path[0] = 'scripts'; "
        "runpy.run_path('scripts/drain_audit_outbox.py', run_name='entrypoint_check')"
    )
    assert result.returncode == 0, result.stderr


def test_the_job_fails_visibly_when_platform_never_becomes_ready(monkeypatch, capsys):
    sys.path.insert(0, str(APP_DIR))
    import scripts.drain_audit_outbox as entry

    outcome = {"delivered": 0, "retried": 0, "refused": 0, "stopped": None}
    monkeypatch.setattr(entry, "drain", lambda db: dict(outcome))
    assert entry.main() == 0
    outcome["stopped"] = "platform_not_ready"
    assert entry.main() == 1
    assert '"stopped": "platform_not_ready"' in capsys.readouterr().out
