from pathlib import Path
import unittest

import yaml


ROOT = Path(__file__).resolve().parents[2]
MANIFEST_DIR = ROOT / "artifacts" / "opentelemetry-demo" / "manifests"


class OtelLabFixtureTests(unittest.TestCase):
    def test_cart_port_is_explicit_and_consistent(self):
        documents = list(
            yaml.safe_load_all((MANIFEST_DIR / "otel_lab_manifest.yaml").read_text())
        )
        cart_deployment = next(
            doc
            for doc in documents
            if doc.get("kind") == "Deployment"
            and doc.get("metadata", {}).get("name") == "cart"
        )
        cart_service = next(
            doc
            for doc in documents
            if doc.get("kind") == "Service"
            and doc.get("metadata", {}).get("name") == "cart"
        )
        port = cart_service["spec"]["ports"][0]
        self.assertEqual(port["port"], 7070)
        self.assertEqual(port["targetPort"], 7070)
        container = cart_deployment["spec"]["template"]["spec"]["containers"][0]
        self.assertEqual(container["ports"][0]["containerPort"], 7070)
        env = {item["name"]: item["value"] for item in container["env"]}
        self.assertEqual(env["ASPNETCORE_URLS"], "http://*:7070")

    def test_checkout_dependencies_needed_by_workload_are_present(self):
        documents = list(
            yaml.safe_load_all((MANIFEST_DIR / "otel_lab_manifest.yaml").read_text())
        )
        deployments = {
            doc["metadata"]["name"]: doc
            for doc in documents
            if doc.get("kind") == "Deployment"
        }
        services = {
            doc["metadata"]["name"]
            for doc in documents
            if doc.get("kind") == "Service"
        }
        self.assertTrue({"quote", "flagd"}.issubset(deployments))
        self.assertTrue({"quote", "flagd"}.issubset(services))
        email = deployments["email"]["spec"]["template"]["spec"]["containers"][0]
        email_env = {item["name"]: item["value"] for item in email["env"]}
        self.assertEqual(email_env["APP_ENV"], "production")
        shipping = deployments["shipping"]["spec"]["template"]["spec"]["containers"][0]
        shipping_env = {item["name"]: item["value"] for item in shipping["env"]}
        self.assertEqual(shipping_env["QUOTE_ADDR"], "http://quote:8090")
        payment = deployments["payment"]["spec"]["template"]["spec"]["containers"][0]
        payment_env = {item["name"]: item["value"] for item in payment["env"]}
        self.assertEqual(payment_env["FLAGD_HOST"], "flagd")
        self.assertEqual(payment_env["FLAGD_PORT"], "8013")

    def test_kustomization_generates_all_referenced_configmaps(self):
        kustomization = yaml.safe_load(
            (MANIFEST_DIR / "kustomization.yaml").read_text()
        )
        generators = {
            item["name"]: item["files"]
            for item in kustomization["configMapGenerator"]
        }
        self.assertEqual(generators["postgres-init"], ["init.sql=init_lite.sql"])
        self.assertEqual(generators["flagd-config"], ["demo.flagd.json"])
        self.assertTrue((MANIFEST_DIR / "init_lite.sql").is_file())
        self.assertTrue((MANIFEST_DIR / "demo.flagd.json").is_file())


if __name__ == "__main__":
    unittest.main()
