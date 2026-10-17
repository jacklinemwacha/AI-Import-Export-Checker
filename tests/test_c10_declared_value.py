import unittest

import helpers
from app.engine.checks import check_c10


def docs(total=4200, currency="USD", declared=4200, bl_currency="USD"):
    return {"commercial_invoice": {"total_value": total, "currency": currency},
            "bill_of_lading": {"declared_value": declared, "currency": bl_currency}}


class TestC10DeclaredValue(unittest.TestCase):
    def setUp(self):
        self.rules = helpers.load_rules()

    # values equal
    def test_equal_values_pass(self):
        r = check_c10(docs(), self.rules)
        self.assertEqual((r.outcome, r.findings), ("pass", []))

    def test_a_difference_of_one_cent_passes(self):
        self.assertEqual(check_c10(docs(declared=4200.01), self.rules).outcome, "pass")

    def test_currency_case_does_not_matter(self):
        self.assertEqual(check_c10(docs(bl_currency="usd"), self.rules).outcome, "pass")

    # values different
    def test_a_different_value_is_a_medium_finding(self):
        r = check_c10(docs(declared=4000), self.rules)
        self.assertEqual(r.outcome, "finding")
        f = r.finding
        self.assertEqual((f.check_id, f.severity, f.field), ("C10", "medium", "declared_value"))
        self.assertEqual(f.documents, ["commercial_invoice", "bill_of_lading"])
        self.assertEqual(f.values, {"commercial_invoice": 4200, "bill_of_lading": 4000})
        self.assertEqual(f.message, "Declared value differs: 4200 USD on the invoice, 4000 USD on the bill of lading.")

    def test_a_difference_of_two_cents_is_a_finding(self):
        self.assertEqual(check_c10(docs(declared=4200.02), self.rules).outcome, "finding")

    def test_different_currencies_are_a_finding(self):
        r = check_c10(docs(bl_currency="EUR"), self.rules)
        self.assertEqual(r.outcome, "finding")
        self.assertEqual(r.finding.message, "Declared value currency differs: USD on the invoice, EUR on the bill of lading.")

    def test_a_missing_currency_means_only_the_amounts_are_compared(self):
        self.assertEqual(check_c10(docs(currency=None, bl_currency=None), self.rules).outcome, "pass")
        r = check_c10(docs(currency=None, bl_currency=None, declared=4000), self.rules)
        self.assertEqual(r.finding.message, "Declared value differs: 4200 on the invoice, 4000 on the bill of lading.")

    def test_the_tolerance_comes_from_the_rule_pack(self):
        self.assertEqual(check_c10(docs(declared=4200.5), dict(self.rules, money_tolerance=1)).outcome, "pass")

    # field missing
    def test_no_declared_value_is_skipped_not_a_finding(self):
        r = check_c10(docs(declared=None), self.rules)
        self.assertEqual((r.outcome, r.findings), ("skipped_not_present", []))

    def test_no_invoice_total_is_skipped(self):
        self.assertEqual(check_c10(docs(total=None), self.rules).outcome, "skipped_not_present")
        self.assertEqual(check_c10({}, self.rules).outcome, "skipped_not_present")

    def test_every_synthetic_set_is_skipped_because_no_bill_of_lading_states_a_value(self):
        for n in range(1, 11):
            self.assertEqual(check_c10(helpers.load_documents(n), self.rules).outcome, "skipped_not_present", f"set {n}")


if __name__ == "__main__":
    unittest.main()
