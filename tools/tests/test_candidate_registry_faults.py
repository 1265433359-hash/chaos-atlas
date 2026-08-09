"""Phase P1-3 tests: candidate registry fault-family parsing + ground truth.

Regression: fault_of must NEVER parse the numeric suffix (OB-CART-DELAY-2000
must be 'delay', not '2000').
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from build_candidate_registry import fault_of, project_of


class FaultFamilyParsingTests(unittest.TestCase):
    def test_delay_with_numeric_suffix(self):
        self.assertEqual(fault_of("OB-CART-DELAY-2000"), "delay")

    def test_loss_with_numeric_suffix(self):
        self.assertEqual(fault_of("OB-CURRENCY-LOSS-100"), "loss")

    def test_kill_no_suffix(self):
        self.assertEqual(fault_of("OB-PRODUCTCATALOG-KILL"), "kill")

    def test_cpu_with_numeric_suffix(self):
        self.assertEqual(fault_of("TT-STATION-CPU-80"), "cpu")

    def test_lowercase_input_normalized(self):
        self.assertEqual(fault_of("sock-orders-payment-delay-2000"), "delay")

    def test_unknown_returns_unknown(self):
        self.assertEqual(fault_of("OB-CHECKOUT"), "unknown")
        self.assertEqual(fault_of("X"), "unknown")

    def test_delay_token_inside_edge_not_mistaken(self):
        # A candidate whose id contains a numeric segment but no fault token.
        self.assertEqual(fault_of("TT-BASIC-DELAY-500"), "delay")

    def test_restart_stress_tokens(self):
        self.assertEqual(fault_of("OB-X-RESTART-1"), "restart")
        self.assertEqual(fault_of("OB-X-STRESS-1"), "stress")


class ProjectParsingTests(unittest.TestCase):
    def test_project_prefixes(self):
        self.assertEqual(project_of("OB-CART-DELAY-2000"), "OB")
        self.assertEqual(project_of("SOCK-ORDERS-PAYMENT-LOSS-100"), "SOCK")
        self.assertEqual(project_of("OTEL-CHECKOUT-LOSS-100"), "OTEL")
        self.assertEqual(project_of("TT-STATION-LOSS-100"), "TT")
        self.assertEqual(project_of("UNKNOWN-X"), "UNKNOWN")


if __name__ == "__main__":
    unittest.main()
