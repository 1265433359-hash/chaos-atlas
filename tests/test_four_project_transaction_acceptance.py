from pathlib import Path

import pytest

from scripts.run_four_project_transaction_acceptance import create_unique_png, verify_png


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
