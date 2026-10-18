import unittest

import helpers
from app.engine.checks import check_c7

GOOD = "MSCU8849201"          # a real-format number with a correct check digit
OTHER = helpers.load_documents(7)["packing_list"]["container_number"]     # another number with a correct check digit


def docs(pl=GOOD, bl=(GOOD,)):
    return {"packing_list": {"container_number": pl}, "bill_of_lading": {"container_numbers": list(bl)}}


class TestC7Container(unittest.TestCase):
    def setUp(self):
        self.rules = helpers.load_rules()

    # values equal
    def test_equal_numbers_pass(self):
        r = check_c7(docs(), self.rules)
        self.assertEqual((r.outcome, r.findings), ("pass", []))

    def test_clean_sets_pass(self):
        for n in (1, 3, 4, 5, 6, 7, 8, 10):
            self.assertEqual(check_c7(helpers.load_documents(n), self.rules).outcome, "pass", f"set {n}")

    def test_spaces_hyphens_and_case_are_ignored(self):
        self.assertEqual(check_c7(docs(pl="mscu 884920-1", bl=("MSCU8849201",)), self.rules).outcome, "pass")

    def test_the_bill_of_lading_may_list_several_containers(self):
        self.assertEqual(check_c7(docs(bl=(OTHER, GOOD)), self.rules).outcome, "pass")

    # values different
    def test_set_9_gives_a_high_finding_for_the_swapped_digits(self):
        r = check_c7(helpers.load_documents(9), self.rules)
        self.assertEqual(r.outcome, "finding")
        f = r.findings[0]
        self.assertEqual((f.check_id, f.severity, f.field), ("C7", "high", "container_number"))
        self.assertEqual(f.documents, ["packing_list", "bill_of_lading"])
        pl = helpers.load_documents(9)["packing_list"]["container_number"]
        bl = helpers.load_documents(9)["bill_of_lading"]["container_numbers"][0]
        self.assertEqual(f.message, f"Container number differs: {pl} on the packing list, {bl} on the bill of lading.")

    def test_a_different_number_is_a_finding(self):
        r = check_c7(docs(bl=(OTHER,)), self.rules)
        self.assertEqual(r.outcome, "finding")
        self.assertEqual(r.findings[0].message, f"Container number differs: MSCU8849201 on the packing list, {OTHER} on the bill of lading.")

    # field missing
    def test_a_missing_number_is_skipped_not_a_finding(self):
        for d in (docs(pl=None), docs(bl=()), docs(pl="", bl=("",)), {}):
            r = check_c7(d, self.rules)
            self.assertEqual((r.outcome, r.findings), ("skipped_not_present", []))

    def test_set_2_has_no_container_on_the_packing_list_so_it_is_skipped(self):
        self.assertEqual(check_c7(helpers.load_documents(2), self.rules).outcome, "skipped_not_present")

    # format and check digit
    def test_a_number_in_the_wrong_format_is_a_finding(self):
        r = check_c7(docs(pl="MSCU88492", bl=("MSCU88492",)), self.rules)
        self.assertEqual(r.outcome, "finding")
        self.assertEqual({f.message for f in r.findings}, {"Container number MSCU88492 is not in a valid format."})

    def test_a_wrong_check_digit_is_a_medium_finding_when_the_rule_is_on(self):
        r = check_c7(docs(pl="MSCU8849200", bl=("MSCU8849200",)), self.rules)
        self.assertEqual(r.outcome, "finding")
        self.assertEqual([f.severity for f in r.findings], ["medium", "medium"])
        self.assertIn("invalid check digit", r.findings[0].message)

    def test_the_check_digit_is_not_checked_when_the_rule_is_off(self):
        rules = dict(self.rules, container_check_digit=False)
        self.assertEqual(check_c7(docs(pl="MSCU8849200", bl=("MSCU8849200",)), rules).outcome, "pass")

    def test_set_9_also_has_an_invalid_check_digit_on_the_bill_of_lading(self):
        r = check_c7(helpers.load_documents(9), self.rules)
        self.assertEqual([f.severity for f in r.findings], ["high", "medium"])


if __name__ == "__main__":
    unittest.main()
