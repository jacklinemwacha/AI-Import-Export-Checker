import unittest

import helpers
from app.engine.checks import check_c8


def docs(inv=("853950",), pl=("853950",), bl=()):
    d = {"commercial_invoice": {"lines": [{"hs_code": c} for c in inv]}, "packing_list": {"hs_codes": list(pl)}}
    d["bill_of_lading"] = {"hs_codes": list(bl)}
    return d


class TestC8HsCode(unittest.TestCase):
    def setUp(self):
        self.rules = helpers.load_rules()

    # values equal
    def test_equal_codes_pass(self):
        r = check_c8(docs(), self.rules)
        self.assertEqual((r.outcome, r.findings), ("pass", []))

    def test_clean_sets_pass_including_twelve_codes_and_a_bill_of_lading_code(self):
        for n in (1, 2, 3, 4, 5, 6, 7, 8, 9):
            self.assertEqual(check_c8(helpers.load_documents(n), self.rules).outcome, "pass", f"set {n}")

    def test_dots_and_spaces_are_ignored(self):
        self.assertEqual(check_c8(docs(inv=("8539.50",), pl=("8539 50",)), self.rules).outcome, "pass")

    def test_only_the_first_six_digits_are_compared(self):
        self.assertEqual(check_c8(docs(inv=("8539.50.00",), pl=("853950",)), self.rules).outcome, "pass")
        self.assertEqual(check_c8(docs(inv=("8539.50.00",), pl=("8539.50.99",)), self.rules).outcome, "pass")

    def test_a_shorter_code_matches_the_start_of_a_longer_one(self):
        self.assertEqual(check_c8(docs(inv=("8539",), pl=("853950",)), self.rules).outcome, "pass")

    def test_several_codes_on_a_document_must_all_appear_on_the_other(self):
        self.assertEqual(check_c8(docs(inv=("853950", "851762"), pl=("851762", "853950")), self.rules).outcome, "pass")

    # values different
    def test_set_10_gives_a_medium_finding(self):
        r = check_c8(helpers.load_documents(10), self.rules)
        self.assertEqual(r.outcome, "finding")
        f = r.finding
        self.assertEqual((f.check_id, f.severity, f.field), ("C8", "medium", "hs_code"))
        self.assertEqual(f.documents, ["commercial_invoice", "packing_list"])
        self.assertEqual(f.values, {"commercial_invoice": "850440", "packing_list": "850450"})
        self.assertEqual(f.message, "HS code differs: 850440 on the invoice, 850450 on the packing list.")

    def test_a_code_missing_on_the_other_document_is_a_finding(self):
        self.assertEqual(check_c8(docs(inv=("853950", "851762"), pl=("853950",)), self.rules).outcome, "finding")

    def test_each_pair_that_disagrees_gives_its_own_finding(self):
        r = check_c8(docs(inv=("853950",), pl=("853950",), bl=("611610",)), self.rules)
        self.assertEqual([f.documents for f in r.findings],
                         [["commercial_invoice", "bill_of_lading"], ["packing_list", "bill_of_lading"]])

    def test_the_digit_count_comes_from_the_rule_pack(self):
        d = docs(inv=("853950",), pl=("853960",))
        self.assertEqual(check_c8(d, self.rules).outcome, "finding")
        self.assertEqual(check_c8(d, dict(self.rules, hs_code_digits=4)).outcome, "pass")

    # field missing
    def test_codes_on_only_one_document_are_skipped_not_a_finding(self):
        for d in (docs(inv=(), pl=("853950",)), docs(inv=(None,), pl=()), {}):
            r = check_c8(d, self.rules)
            self.assertEqual((r.outcome, r.findings), ("skipped_not_present", []))

    def test_a_short_number_is_not_a_plausible_code(self):
        self.assertEqual(check_c8(docs(inv=("85",), pl=("853950",)), self.rules).outcome, "skipped_not_present")


if __name__ == "__main__":
    unittest.main()
