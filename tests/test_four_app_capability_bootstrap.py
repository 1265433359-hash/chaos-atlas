import json
from pathlib import Path

import pytest

from chaosatlas.capabilities.bootstrap import CapabilityBootstrapper


ROOT = Path(__file__).resolve().parents[1]
PROFILE_PATHS = [
    ROOT / "projects" / "chaosatlas-apps" / project / "profile.json"
    for project in ("immich", "erpnext", "medusa", "rocketchat")
]


class _ReadOnlyAdapter:
    kube_context = "chaosatlas-apps"

    def __init__(self, profile):
        self.profile = profile

    def inventory(self):
        return {
            "status": "verified",
            "project_id": self.profile["project_id"],
            "project_commit": self.profile["project_commit"],
            "namespace": self.profile["namespace_policy"]["allowed_namespaces"][0],
            "dependencies": [],
            "warnings": [],
        }

    def build_capability_nodes(self, _inventory):
        project = self.profile["project_id"]
        return {
            "status": "verified",
            "deployment_nodes": [{
                "node_id": f"node:{project}",
                "deployment": {"name": project, "workload_kind": "Deployment", "containers": [project]},
                "service": {"name": project},
                "extensions": {"runtime": {"jvm_present": False}, "capabilities": {}, "resource_facts": {}},
            }],
            "errors": [],
        }

    def runner(self, args, timeout=30):
        command = args[2:] if args[:2] == ["--context", "chaosatlas-apps"] else args
        assert command[0] == "get"
        if command[:2] == ["get", "crd"]:
            return 0, "ok", ""
        return 0, '{"items": []}', ""


@pytest.mark.parametrize("profile_path", PROFILE_PATHS)
def test_each_four_app_profile_produces_complete_read_only_catalog(profile_path):
    profile = json.loads(profile_path.read_text(encoding="utf-8-sig"))
    result = CapabilityBootstrapper(profile=profile, adapter=_ReadOnlyAdapter(profile)).run()
    assert result["status"] == "verified"
    assert result["catalog"] == {"core": 32, "extension": 9, "total": 41}
    assert len(result["project_capabilities"]) == 41
    assert result["read_only"] is True
    assert result["injection_performed"] is False
