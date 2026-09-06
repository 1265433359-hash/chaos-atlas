from pathlib import Path

import pytest

from scripts.run_four_project_transaction_acceptance import (
    _journal_write_count,
    _transaction_command,
    create_unique_png,
    verify_png,
)


def test_unique_png_is_validated_and_changes_per_run(tmp_path: Path):
    first, second = tmp_path / "first.png", tmp_path / "second.png"
    first_report = create_unique_png(first)
    second_report = create_unique_png(second)
    assert first_report == verify_png(first)
    assert first_report["width"] == first_report["height"] == 2
    assert first_report["sha256"] != second_report["sha256"]


def test_png_decoder_rejects_corrupted_fixture(tmp_path: Path):
    path = tmp_path / "fixture.png"
    create_unique_png(path)
    payload = bytearray(path.read_bytes())
    payload[-5] ^= 0xFF
    path.write_bytes(payload)
    with pytest.raises(ValueError, match="checksum"):
        verify_png(path)


def test_cross_process_command_pins_scenario_and_exact_crash_marker(tmp_path: Path):
    marker = tmp_path / "crash" / "crash-window.json"
    command = _transaction_command(
        contract=Path("contract.json"), store=tmp_path / "state",
        lease_id="lease-test", service="app", port=8080,
        fixtures=tmp_path / "fixtures.json", evidence=tmp_path / "crash",
        run_id="run-test", scenario="crash-after-response", crash_marker=marker,
    )
    assert command[command.index("--scenario") + 1] == "crash-after-response"
    assert command[command.index("--crash-marker") + 1] == str(marker)
    assert command.count("--lease-id") == 1


def test_journal_write_count_does_not_treat_acceptance_event_as_second_write(tmp_path: Path):
    journal = tmp_path / "journal.jsonl"
    journal.write_text(
        '{"event":"request","method":"POST"}\n'
        '{"event":"external_termination_window_open","method":"POST"}\n'
        '{"event":"request","method":"GET"}\n',
        encoding="utf-8",
    )
    assert _journal_write_count(journal) == 1
    assert _journal_write_count(tmp_path / "no-recovery-requests.jsonl") == 0
