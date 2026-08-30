import json
from pathlib import Path

from scripts.run_fault_matrix import build_report


def test_matrix_report_lists_all_projects_and_32_faults():
    paths = [
        Path("projects/nginx-kubernetes-ingress/profile.json"),
        Path("projects/sock-shop/profile.json"),
        Path("projects/online-boutique/profile.json"),
    ]

    report = build_report(paths)

    assert report["schema_version"] == "chaosatlas-fault-matrix-report-v1"
    assert len(report["projects"]) == 3
    assert all(item["fault_count"] == 32 for item in report["projects"])
    assert report["aggregate"]["faults"] == 32
