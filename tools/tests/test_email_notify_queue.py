import importlib.util
import json
from pathlib import Path


MODULE_PATH = (
    Path.home()
    / ".codex"
    / "skills"
    / "email-notify"
    / "scripts"
    / "notification_queue.py"
)


def load_module():
    spec = importlib.util.spec_from_file_location("notification_queue", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_notification_subject_and_body_are_project_aware():
    module = load_module()

    assert module.build_subject("ChaosAtlas", "Run checks") == "[ChaosAtlas] Run checks"
    assert module.build_subject("ChaosAtlas", "[ChaosAtlas] Run checks") == "[ChaosAtlas] Run checks"

    body = module.build_body(
        machine_name="XIAO-Windows",
        project_name="ChaosAtlas",
        session_name="Run checks",
        status="blocked",
        summary="Waiting for the external service.",
    )
    assert "Project: ChaosAtlas" in body
    assert "Session: Run checks" in body
    assert "Result: blocked" in body


def test_enqueue_writes_only_notification_metadata(tmp_path):
    module = load_module()
    queue = module.NotificationQueue(tmp_path)

    path = queue.enqueue(
        project_name="ChaosAtlas",
        session_name="Run checks",
        status="success",
        summary="Tests passed.",
        machine_name="XIAO-Windows",
    )

    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["project_name"] == "ChaosAtlas"
    assert payload["session_name"] == "Run checks"
    assert payload["status"] == "success"
    assert "password" not in json.dumps(payload).lower()
    assert "api_key" not in json.dumps(payload).lower()
    assert path.parent.name == "pending"


def test_failed_delivery_increments_attempts_and_moves_to_failed(tmp_path):
    module = load_module()
    queue = module.NotificationQueue(tmp_path, max_attempts=1)
    pending = queue.enqueue(
        project_name="ChaosAtlas",
        session_name="Run checks",
        status="failed",
        summary="Verification failed.",
        machine_name="XIAO-Windows",
    )

    queue.record_failure(pending, "network denied")

    failed = list((tmp_path / "failed").glob("*.json"))
    assert len(failed) == 1
    payload = json.loads(failed[0].read_text(encoding="utf-8"))
    assert payload["attempts"] == 1
    assert payload["last_error"] == "network denied"


def test_successful_delivery_moves_message_to_sent(tmp_path):
    module = load_module()
    queue = module.NotificationQueue(tmp_path)
    queue.enqueue(
        project_name="ChaosAtlas",
        session_name="Run checks",
        status="success",
        summary="Verification passed.",
        machine_name="XIAO-Windows",
    )

    counts = queue.process_once(sender=lambda payload, timeout: None)

    assert counts == {"sent": 1, "retrying": 0, "failed": 0}
    assert len(list((tmp_path / "pending").glob("*.json"))) == 0
    assert len(list((tmp_path / "sent").glob("*.json"))) == 1


def test_worker_recovers_message_left_in_sending(tmp_path):
    module = load_module()
    queue = module.NotificationQueue(tmp_path)
    pending = queue.enqueue(
        project_name="ChaosAtlas",
        session_name="Recover message",
        status="partial",
        summary="Recover a worker interruption.",
        machine_name="XIAO-Windows",
    )
    sending = tmp_path / "sending" / pending.name
    pending.replace(sending)

    counts = queue.process_once(sender=lambda payload, timeout: None)

    assert counts == {"sent": 1, "retrying": 0, "failed": 0}
    assert len(list((tmp_path / "sent").glob("*.json"))) == 1
