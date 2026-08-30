from scripts.runtime_env import runtime_env


def test_runtime_env_prefers_readable_local_packages(tmp_path, monkeypatch):
    packages = tmp_path / "ChaosAtlas" / "python-packages"
    (packages / "yaml").mkdir(parents=True)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setenv("PYTHONPATH", "old-path")

    env = runtime_env()

    assert env["PYTHONPATH"].split(";")[0] == str(packages)
    assert "old-path" in env["PYTHONPATH"]
