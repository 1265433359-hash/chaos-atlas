import importlib.util
import sys
from pathlib import Path


SCRIPT_PATH = (
    Path.home()
    / ".codex"
    / "skills"
    / "email-notify"
    / "scripts"
    / "send_email_notification.py"
)
SCRIPT_DIR = SCRIPT_PATH.parent


def load_email_notify():
    if str(SCRIPT_DIR) not in sys.path:
        sys.path.insert(0, str(SCRIPT_DIR))
    spec = importlib.util.spec_from_file_location("email_notify", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_subject_uses_dynamic_project_prefix_without_duplication():
    module = load_email_notify()

    assert module._build_subject("ChaosAtlas", "Run checks") == "[ChaosAtlas] Run checks"
    assert module._build_subject("ChaosAtlas", "[ChaosAtlas] Run checks") == "[ChaosAtlas] Run checks"


def test_body_reports_project_session_and_result():
    module = load_email_notify()

    body = module._build_body(
        machine_name="XIAO-Windows",
        project_name="ChaosAtlas",
        session_name="Run checks",
        status="blocked",
        summary="Waiting for the external service.",
    )

    assert "Project: ChaosAtlas" in body
    assert "Session: Run checks" in body
    assert "Result: blocked" in body
    assert "Summary: Waiting for the external service." in body
