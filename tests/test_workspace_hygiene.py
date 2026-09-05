def test_state_root_prefers_explicit_override(tmp_path):
    from chaosatlas.workspace import archive_root, runs_root, state_root, temporary_root

    configured = tmp_path / "external-state"
    env = {"CHAOSATLAS_STATE_ROOT": str(configured), "LOCALAPPDATA": str(tmp_path / "ignored")}

    assert state_root(env) == configured.resolve()
    assert runs_root(env) == configured.resolve() / "runs"
    assert temporary_root(env) == configured.resolve() / "tmp"
    assert archive_root(env) == configured.resolve() / "archive"


def test_state_root_uses_local_app_data_on_windows_style_environment(tmp_path):
    from chaosatlas.workspace import state_root

    assert state_root({"LOCALAPPDATA": str(tmp_path)}) == (tmp_path / "ChaosAtlas").resolve()


def test_hygiene_finds_runtime_state_and_nested_dependencies(tmp_path):
    from scripts.check_workspace_hygiene import find_workspace_leaks

    (tmp_path / ".runs").mkdir()
    (tmp_path / ".tmp-old").mkdir()
    (tmp_path / "projects" / "chaosatlas-apps" / "medusa" / "node_modules").mkdir(parents=True)
    (tmp_path / "src" / "chaosatlas" / "__pycache__").mkdir(parents=True)
    (tmp_path / "src" / "chaosatlas.egg-info").mkdir()

    assert find_workspace_leaks(tmp_path) == [
        ".runs",
        ".tmp-old",
        "projects/chaosatlas-apps/medusa/node_modules",
        "src/chaosatlas.egg-info",
        "src/chaosatlas/__pycache__",
    ]


def test_hygiene_allows_curated_evidence_and_required_local_environments(tmp_path):
    from scripts.check_workspace_hygiene import find_workspace_leaks

    for relative in ("artifacts/reviewed", "reporting/issues", ".venv", ".secrets"):
        (tmp_path / relative).mkdir(parents=True)

    assert find_workspace_leaks(tmp_path) == []
