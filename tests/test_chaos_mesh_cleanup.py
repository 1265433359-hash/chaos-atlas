import json

from tools.chaos_mesh_cleanup import cleanup_namespace_chaos_resources


def test_cleanup_deletes_owned_resources_and_target_pod_children():
    deleted = []

    def runner(args, timeout=30, kube_context=None):
        if args[0] == "api-resources":
            return 0, "podnetworkchaos.chaos-mesh.org\nnetworkchaos.chaos-mesh.org\n", ""
        if args[0] == "get" and len(args) == 6:
            resource = args[1]
            if resource == "podnetworkchaos.chaos-mesh.org":
                return 0, json.dumps({"items": [{
                    "metadata": {
                        "name": "child",
                        "labels": {"chaosatlas.dev/cleanup-owner": "chaosatlas"},
                    }
                }]}), ""
            return 0, json.dumps({"items": []}), ""
        if args[0] == "delete":
            deleted.append((args[1], args[2]))
            return 0, "deleted", ""
        if args[0] == "get" and len(args) == 7:
            return 1, "", "Error from server (NotFound): not found"
        raise AssertionError(args)

    report = cleanup_namespace_chaos_resources("lab", runner=runner)

    assert report["status"] == "verified"
    assert report["confirmed"] is True
    assert deleted == [("podnetworkchaos.chaos-mesh.org", "child")]
    assert report["residual_count"] == 0


def test_cleanup_fails_closed_for_unowned_residue():
    def runner(args, timeout=30, kube_context=None):
        if args[0] == "api-resources":
            return 0, "podnetworkchaos.chaos-mesh.org\n", ""
        if args[0] == "get":
            return 0, json.dumps({"items": [{"metadata": {"name": "foreign"}}]}), ""
        raise AssertionError(args)

    report = cleanup_namespace_chaos_resources("lab", runner=runner)

    assert report["status"] == "failed"
    assert report["confirmed"] is False
    assert report["unowned_resources"][0]["name"] == "foreign"
