import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from project_registry import fault_of, normalize_service, project_of  # noqa: E402


class SockShopProjectRegistryTests(unittest.TestCase):
    """Project-aware normalization must handle Sock Shop (4th project)."""

    def test_sock_prefix_normalization(self):
        self.assertEqual(project_of("SOCK-CARTS-LOSS-100"), "SOCK")
        self.assertEqual(normalize_service("SOCK-CARTS-LOSS-100"), "CART")
        self.assertEqual(normalize_service("SOCK-ORDERS-DELAY-2000"), "ORDER")
        self.assertEqual(normalize_service("SOCK-CATALOGUE-LOSS-100"), "CATALOGUE")
        self.assertEqual(fault_of("SOCK-PAYMENT-LOSS-100"), "loss")

    def test_plural_singular_normalization(self):
        self.assertEqual(normalize_service("SOCK-CARTS-DELAY-2000"), "CART")
        self.assertEqual(normalize_service("SOCK-ORDERS-DELAY-2000"), "ORDER")

    def test_legacy_projects_unaffected(self):
        self.assertEqual(normalize_service("OB-PAYMENT-LOSS-100"), "PAYMENT")
        self.assertEqual(normalize_service("OTEL-EMAIL-DELAY-2000"), "EMAIL")
        self.assertEqual(normalize_service("TT-BASIC-DELAY-100"), "BASIC")


if __name__ == "__main__":
    unittest.main()
