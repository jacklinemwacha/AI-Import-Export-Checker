"""The checks. Each check takes the confirmed documents and the rule pack and returns a CheckResult.

`documents` is a dict like the "documents" part of a setNN_expected.json file:
    {"commercial_invoice": {...}, "packing_list": {...}, "bill_of_lading": {...}}
A missing field is never a mismatch: the check is skipped and recorded as "skipped_not_present".
"""
import re
from decimal import Decimal, InvalidOperation
from difflib import SequenceMatcher
from itertools import combinations

from .models import CheckResult, Finding

LB_TO_KG = Decimal("0.45359237")
TYPE_SYNONYMS = {"ctn": "carton", "ctns": "carton", "plt": "pallet", "plts": "pallet"}
UNIT_SYNONYMS = {"pc": "piece", "pcs": "piece", "piece": "piece", "pieces": "piece", "unit": "piece", "units": "piece"}
COMPANY_SUFFIXES = {"ltd", "limited", "co", "company", "llc", "inc", "gmbh", "corp", "corporation", "plc"}
DOC_LABEL = {"commercial_invoice": "invoice", "packing_list": "packing list", "bill_of_lading": "bill of lading"}


# ---------- small helpers ----------
def _num(value):
    """A JSON number as a Decimal, or None if it is missing or not a number."""
    if value is None or isinstance(value, bool):
        return None
    try:
        return Decimal(str(value))
    except InvalidOperation:
        return None


def _fmt(d):
    """Format a Decimal for a message: 2500 -> '2500', 45.359237 -> '45.36'."""
    s = format(d.quantize(Decimal("0.01")), "f")
    return s.rstrip("0").rstrip(".") if "." in s else s


def _json_num(d):
    """A Decimal as a plain JSON number: int when whole, otherwise rounded to 2 decimals."""
    q = d.quantize(Decimal("0.01"))
    return int(q) if q == q.to_integral_value() else float(q)


def _to_kg(value, unit):
    """Convert a weight to kilograms. Returns None if the unit is missing or not recognised."""
    n = _num(value)
    u = (unit or "").strip().lower()
    if n is None:
        return None
    if u in ("kg", "kgs", "kilogram", "kilograms"):
        return n
    if u in ("lb", "lbs", "pound", "pounds"):
        return n * LB_TO_KG
    return None


def _norm_word(word, synonyms=None):
    """'Cartons', 'carton' and 'ctns' all become 'carton'. None if the word is missing."""
    if word is None:
        return None
    s = str(word).strip().lower()
    if not s:
        return None
    s = (synonyms or {}).get(s, s)
    if s.endswith("es") and s[:-2].endswith(("x", "s", "ch", "sh")):
        s = s[:-2]
    elif s.endswith("s") and not s.endswith("ss"):
        s = s[:-1]
    return (synonyms or {}).get(s, s)


def _norm_type(package_type):
    return _norm_word(package_type, TYPE_SYNONYMS)


def _norm_unit(unit):
    return _norm_word(unit, UNIT_SYNONYMS)


def _tidy_name(name):
    """Lower case, no punctuation, no company suffix: 'EXAMPLE Imports, Ltd.' -> 'example imports'."""
    if name is None:
        return ""
    words = re.sub(r"[^a-z0-9 ]", " ", str(name).lower()).split()
    return " ".join(w for w in words if w not in COMPANY_SUFFIXES)


def _label(count, package_type):
    """'2 pallets', '1 pallet', '25 cartons'."""
    if package_type is None:
        return _fmt(count)
    if count != 1:
        package_type += "es" if package_type.endswith(("s", "x", "ch", "sh")) else "s"
    return f"{_fmt(count)} {package_type}"


# ---------- C3: gross weight (packing list against bill of lading) ----------
def check_c3(documents, rules):
    """Gross weights must be equal within the tolerance in the rule pack (1 percent to start).
    The percentage is measured against the packing list value. Invoices are left out
    because their weight is not labelled gross or net."""
    pl = documents.get("packing_list") or {}
    bl = documents.get("bill_of_lading") or {}
    raw_a, raw_b = pl.get("total_gross_weight"), bl.get("gross_weight")
    if _num(raw_a) is None or _num(raw_b) is None:
        return CheckResult("C3", "skipped_not_present", note="Gross weight is not present on both documents.")

    a = _to_kg(raw_a, pl.get("weight_unit"))
    b = _to_kg(raw_b, bl.get("weight_unit"))
    if a is None or b is None:
        finding = Finding(
            "C3", "low", ["packing_list", "bill_of_lading"], "gross_weight",
            {"packing_list": f"{raw_a} {pl.get('weight_unit')}", "bill_of_lading": f"{raw_b} {bl.get('weight_unit')}"},
            "Gross weight cannot be compared because the weight unit is missing or not recognised. Please confirm.")
        return CheckResult("C3", "cannot_compare", finding)

    tolerance = Decimal(str(rules["weight_tolerance_percent"]))
    difference = abs(a - b)
    reference = a if a != 0 else b
    if reference == 0 or difference <= reference * tolerance / Decimal(100):
        return CheckResult("C3", "pass")

    percent = (difference / reference * 100).quantize(Decimal("0.1"))
    finding = Finding(
        "C3", "high", ["packing_list", "bill_of_lading"], "gross_weight",
        {"packing_list": _json_num(a), "bill_of_lading": _json_num(b)},
        f"Gross weight differs by {_fmt(difference)} kg ({_fmt(percent)} percent): "
        f"{_fmt(a)} kg on the packing list, {_fmt(b)} kg on the bill of lading.")
    return CheckResult("C3", "finding", finding)


# ---------- C4: number of packages (packing list against bill of lading) ----------
def check_c4(documents, rules):
    """Package counts must match exactly, but only when the package type is the same.
    If both types are known and differ (pallets and cartons), the check cannot compare them
    and returns a Low finding asking for confirmation. If a type is missing, the counts are
    compared as they are."""
    pl = documents.get("packing_list") or {}
    bl = documents.get("bill_of_lading") or {}
    a, b = _num(pl.get("packages")), _num(bl.get("packages"))
    if a is None or b is None:
        return CheckResult("C4", "skipped_not_present", note="The number of packages is not present on both documents.")

    type_a, type_b = _norm_type(pl.get("package_type")), _norm_type(bl.get("package_type"))
    if type_a and type_b and type_a != type_b:
        label_a, label_b = _label(a, type_a), _label(b, type_b)
        finding = Finding(
            "C4", "low", ["packing_list", "bill_of_lading"], "packages",
            {"packing_list": label_a, "bill_of_lading": label_b},
            f"Packages cannot be compared: {label_a} on the packing list, {label_b} on the bill of lading. Please confirm.")
        return CheckResult("C4", "cannot_compare", finding)

    if a == b:
        return CheckResult("C4", "pass")

    finding = Finding(
        "C4", "high", ["packing_list", "bill_of_lading"], "packages",
        {"packing_list": _json_num(a), "bill_of_lading": _json_num(b)},
        f"Number of packages differs: {_fmt(a)} on the packing list, {_fmt(b)} on the bill of lading.")
    return CheckResult("C4", "finding", finding)


# ---------- C1 and C2: names of the parties (all three documents) ----------
def _check_names(check_id, label, field, getters, documents, rules):
    """Compare the names on every pair of documents that carry one. A name is tidied first
    (lower case, no punctuation, no company suffix) and must then be similar enough to pass."""
    threshold = float(rules["name_similarity_threshold"])
    names = []
    for doc_key, getter in getters:
        printed = getter(documents.get(doc_key) or {})
        tidy = _tidy_name(printed)
        if tidy:
            names.append((doc_key, str(printed).strip(), tidy))
    if len(names) < 2:
        return CheckResult(check_id, "skipped_not_present", note=f"The {label} name is present on fewer than two documents.")

    findings = []
    for (doc_a, name_a, tidy_a), (doc_b, name_b, tidy_b) in combinations(names, 2):
        if SequenceMatcher(None, tidy_a, tidy_b).ratio() >= threshold:
            continue
        findings.append(Finding(
            check_id, "high", [doc_a, doc_b], field, {doc_a: name_a, doc_b: name_b},
            f'{label.capitalize()} name differs: "{name_a}" on the {DOC_LABEL[doc_a]}, "{name_b}" on the {DOC_LABEL[doc_b]}.'))
    return CheckResult(check_id, "finding" if findings else "pass", findings=findings)


def check_c1(documents, rules):
    """Consignee name. The invoice buyer, packing list consignee and bill of lading consignee
    must be equal or nearly equal after tidying."""
    getters = [("commercial_invoice", lambda d: (d.get("buyer") or {}).get("name")),
               ("packing_list", lambda d: (d.get("consignee") or {}).get("name")),
               ("bill_of_lading", lambda d: (d.get("consignee") or {}).get("name"))]
    return _check_names("C1", "consignee", "consignee.name", getters, documents, rules)


def check_c2(documents, rules):
    """Shipper name. The invoice seller, packing list shipper and bill of lading shipper."""
    getters = [("commercial_invoice", lambda d: (d.get("seller") or {}).get("name")),
               ("packing_list", lambda d: (d.get("shipper") or {}).get("name")),
               ("bill_of_lading", lambda d: (d.get("shipper") or {}).get("name"))]
    return _check_names("C2", "shipper", "shipper.name", getters, documents, rules)


# ---------- C5: quantity in units (invoice against packing list) ----------
def _quantities_by_unit(doc):
    """{'piece': Decimal(5000), ...} from lines[].quantity. None if there are no lines or a quantity is missing."""
    lines = doc.get("lines") or []
    if not lines:
        return None
    totals = {}
    for line in lines:
        q = _num((line or {}).get("quantity"))
        if q is None:
            return None
        unit = _norm_unit((line or {}).get("unit"))
        totals[unit] = totals.get(unit, Decimal(0)) + q
    return totals


def _units_label(totals):
    return ", ".join(_label(v, u) for u, v in sorted(totals.items(), key=lambda kv: str(kv[0])))


def check_c5(documents, rules):
    """Total quantity must be exactly equal on the invoice and the packing list, for the same unit of
    measure. If both documents name their units and the units differ (pieces and sets), the check
    cannot compare them. Several units on one document are compared unit by unit."""
    inv = _quantities_by_unit(documents.get("commercial_invoice") or {})
    pl = _quantities_by_unit(documents.get("packing_list") or {})
    if inv is None or pl is None:
        return CheckResult("C5", "skipped_not_present", note="The quantity is not present on both documents.")

    docs = ["commercial_invoice", "packing_list"]
    all_known = None not in inv and None not in pl
    if all_known and set(inv) != set(pl):
        a, b = _units_label(inv), _units_label(pl)
        finding = Finding("C5", "low", docs, "quantity", {docs[0]: a, docs[1]: b},
                          f"Quantity cannot be compared: {a} on the invoice, {b} on the packing list. Please confirm.")
        return CheckResult("C5", "cannot_compare", finding)

    if all_known:
        pairs = [(unit, inv[unit], pl[unit]) for unit in sorted(inv)]
    else:
        pairs = [(None, sum(inv.values()), sum(pl.values()))]
    findings = []
    for unit, a, b in pairs:
        if a == b:
            continue
        where = f" ({unit})" if unit and len(pairs) > 1 else ""
        findings.append(Finding("C5", "high", docs, "quantity", {docs[0]: _json_num(a), docs[1]: _json_num(b)},
                                f"Quantity differs{where}: {_fmt(a)} on the invoice, {_fmt(b)} on the packing list."))
    return CheckResult("C5", "finding" if findings else "pass", findings=findings)


# ---------- C6: invoice arithmetic (inside the invoice) ----------
def check_c6(documents, rules):
    """Each line total must equal quantity times unit price, and the lines must add up to the stated
    subtotal (or, when there is no subtotal, the stated total value), within the money tolerance.
    A line with a missing number is skipped. If the invoice shows tax or discounts, the extractor
    should return the subtotal, because the total value then includes them."""
    inv = documents.get("commercial_invoice") or {}
    tolerance = Decimal(str(rules["money_tolerance"]))
    lines = inv.get("lines") or []
    findings, compared, line_totals = [], 0, []
    for n, line in enumerate(lines, start=1):
        line = line or {}
        quantity, price, stated = _num(line.get("quantity")), _num(line.get("unit_price")), _num(line.get("line_total"))
        line_totals.append(stated)
        if quantity is None or price is None or stated is None:
            continue
        compared += 1
        expected = quantity * price
        if abs(expected - stated) > tolerance:
            findings.append(Finding(
                "C6", "high", ["commercial_invoice"], f"lines[{n}].line_total",
                {"quantity": _json_num(quantity), "unit_price": _json_num(price), "expected": _json_num(expected), "stated": _json_num(stated)},
                f"Invoice line {n}: {_fmt(quantity)} x {_fmt(price)} is {_fmt(expected)}, but the line total is {_fmt(stated)}."))

    field, reference = "subtotal", _num(inv.get("subtotal"))
    if reference is None:
        field, reference = "total_value", _num(inv.get("total_value"))
    if lines and reference is not None and all(t is not None for t in line_totals):
        compared += 1
        total = sum(line_totals)
        if abs(total - reference) > tolerance:
            word = "subtotal" if field == "subtotal" else "total"
            findings.append(Finding(
                "C6", "high", ["commercial_invoice"], field, {"lines_sum": _json_num(total), "stated": _json_num(reference)},
                f"Invoice lines add up to {_fmt(total)}, but the stated {word} is {_fmt(reference)}."))

    if findings:
        return CheckResult("C6", "finding", findings=findings)
    if compared == 0:
        return CheckResult("C6", "skipped_not_present", note="The invoice has no complete lines or total to check.")
    return CheckResult("C6", "pass")


# ---------- C7: container number (packing list against bill of lading) ----------
CONTAINER_FORMAT = re.compile(r"^[A-Z]{4}\d{7}$")      # four letters, seven digits


def _tidy_container(value):
    return re.sub(r"[\s.\-]", "", str(value)).upper() if value is not None else ""


def _container_check_digit_ok(code):
    """ISO 6346: the last digit is calculated from the first ten characters."""
    values, v = {}, 10
    for ch in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
        if v % 11 == 0:
            v += 1
        values[ch] = v
        v += 1
    total = sum((values[c] if c.isalpha() else int(c)) * (2 ** i) for i, c in enumerate(code[:10]))
    return total % 11 % 10 == int(code[10])


def check_c7(documents, rules):
    """The packing list container must be one of the bill of lading containers (the bill may list several).
    Spaces, hyphens and case are ignored. Each number must be in a valid format (four letters, seven digits).
    If the rule pack setting container_check_digit is true, the check digit is verified too (Medium)."""
    pl = documents.get("packing_list") or {}
    bl = documents.get("bill_of_lading") or {}
    raw_a = pl.get("container_number")
    a = _tidy_container(raw_a)
    bs = [(str(raw).strip(), _tidy_container(raw)) for raw in (bl.get("container_numbers") or []) if _tidy_container(raw)]
    if not a or not bs:
        return CheckResult("C7", "skipped_not_present", note="The container number is not present on both documents.")

    entries = [("packing_list", str(raw_a).strip(), a)] + [("bill_of_lading", raw, t) for raw, t in bs]
    findings = [Finding("C7", "high", [doc], "container_number", {doc: raw}, f"Container number {raw} is not in a valid format.")
                for doc, raw, tidy in entries if not CONTAINER_FORMAT.match(tidy)]
    if findings:
        return CheckResult("C7", "finding", findings=findings)

    docs = ["packing_list", "bill_of_lading"]
    if a not in {t for _, t in bs}:
        printed = ", ".join(raw for raw, _ in bs)
        findings.append(Finding("C7", "high", docs, "container_number", {docs[0]: str(raw_a).strip(), docs[1]: printed},
                                f"Container number differs: {str(raw_a).strip()} on the packing list, {printed} on the bill of lading."))
    if rules.get("container_check_digit"):
        for doc, raw, tidy in entries:
            if not _container_check_digit_ok(tidy):
                findings.append(Finding("C7", "medium", [doc], "container_number", {doc: raw},
                                        f"Container number {raw} on the {DOC_LABEL[doc]} has an invalid check digit. Please check it."))
    return CheckResult("C7", "finding" if findings else "pass", findings=findings)


# ---------- C8: HS code (any two documents that carry it) ----------
def _hs_codes(doc_key, doc):
    """[(printed, digits)] for every plausible HS code on the document (at least four digits)."""
    if doc_key == "commercial_invoice":
        raw = [(line or {}).get("hs_code") for line in (doc.get("lines") or [])]
    else:
        raw = doc.get("hs_codes") or []
    out, seen = [], set()
    for r in raw:
        if r is None:
            continue
        digits = re.sub(r"\D", "", str(r))
        if len(digits) >= 4 and digits not in seen:
            seen.add(digits)
            out.append((str(r).strip(), digits))
    return out


def check_c8(documents, rules):
    """Compare HS codes on every pair of documents that carry them: digits only, the first hs_code_digits
    digits (6 in the rule pack). Every code on one document must appear on the other. Medium."""
    n = int(rules.get("hs_code_digits", 6))
    present = []
    for key in ("commercial_invoice", "packing_list", "bill_of_lading"):
        codes = _hs_codes(key, documents.get(key) or {})
        if codes:
            present.append((key, codes))
    if len(present) < 2:
        return CheckResult("C8", "skipped_not_present", note="HS codes are present on fewer than two documents.")

    def same(a, b):
        k = min(len(a), len(b), n)
        return a[:k] == b[:k]

    findings = []
    for (doc_a, codes_a), (doc_b, codes_b) in combinations(present, 2):
        ok = all(any(same(x[1], y[1]) for y in codes_b) for x in codes_a) and all(any(same(y[1], x[1]) for x in codes_a) for y in codes_b)
        if ok:
            continue
        a, b = ", ".join(c[0] for c in codes_a), ", ".join(c[0] for c in codes_b)
        findings.append(Finding("C8", "medium", [doc_a, doc_b], "hs_code", {doc_a: a, doc_b: b},
                                f"HS code differs: {a} on the {DOC_LABEL[doc_a]}, {b} on the {DOC_LABEL[doc_b]}."))
    return CheckResult("C8", "finding" if findings else "pass", findings=findings)


# ---------- C9: description of goods (all three documents) ----------
STOP_WORDS = {"and", "the", "for", "with", "from", "per", "are", "all", "etc"}


def _description_tokens(text):
    words = re.findall(r"[a-z]+", str(text).lower())
    return {_norm_word(w) for w in words if len(w) >= 3 and w not in STOP_WORDS}


def _description_text(key, doc):
    if key == "description_of_goods":
        return doc.get("description_of_goods") or ""
    return " ".join(str((line or {}).get("description") or "") for line in (doc.get("lines") or [])).strip()


def check_c9(documents, rules):
    """The descriptions must share enough words, measured against the shorter description (a bill of lading
    description is often brief). Otherwise a person should look: Low severity, wording fixed."""
    threshold = float(rules.get("description_overlap_threshold", 0.3))
    present = []
    for key, getter in (("commercial_invoice", "lines"), ("packing_list", "lines"), ("bill_of_lading", "description_of_goods")):
        text = _description_text(getter, documents.get(key) or {})
        tokens = _description_tokens(text)
        if tokens:
            present.append((key, text, tokens))
    if len(present) < 2:
        return CheckResult("C9", "skipped_not_present", note="The description is present on fewer than two documents.")

    findings = []
    for (doc_a, text_a, tok_a), (doc_b, text_b, tok_b) in combinations(present, 2):
        if len(tok_a & tok_b) / min(len(tok_a), len(tok_b)) >= threshold:
            continue
        findings.append(Finding("C9", "low", [doc_a, doc_b], "description", {doc_a: text_a[:200], doc_b: text_b[:200]},
                                "The descriptions of goods share few words. Please check that they describe the same goods."))
    return CheckResult("C9", "finding" if findings else "pass", findings=findings)


# ---------- C10: declared value (invoice against bill of lading, only when the bill states one) ----------
def check_c10(documents, rules):
    """Total value and currency must be equal. Skipped when the bill of lading has no declared value
    (it was missing on all our samples). Medium."""
    inv = documents.get("commercial_invoice") or {}
    bl = documents.get("bill_of_lading") or {}
    a, b = _num(inv.get("total_value")), _num(bl.get("declared_value"))
    if a is None or b is None:
        return CheckResult("C10", "skipped_not_present", note="No declared value on the bill of lading, or no total on the invoice.")

    docs = ["commercial_invoice", "bill_of_lading"]
    cur_a, cur_b = (inv.get("currency") or "").strip().upper(), (bl.get("currency") or "").strip().upper()
    if cur_a and cur_b and cur_a != cur_b:
        finding = Finding("C10", "medium", docs, "currency", {docs[0]: cur_a, docs[1]: cur_b},
                          f"Declared value currency differs: {cur_a} on the invoice, {cur_b} on the bill of lading.")
        return CheckResult("C10", "finding", finding)
    if abs(a - b) <= Decimal(str(rules["money_tolerance"])):
        return CheckResult("C10", "pass")
    cur = cur_a or cur_b
    unit = f" {cur}" if cur else ""
    finding = Finding("C10", "medium", docs, "declared_value", {docs[0]: _json_num(a), docs[1]: _json_num(b)},
                      f"Declared value differs: {_fmt(a)}{unit} on the invoice, {_fmt(b)}{unit} on the bill of lading.")
    return CheckResult("C10", "finding", finding)


# ---------- runner ----------
CHECKS = [check_c1, check_c2, check_c3, check_c4, check_c5, check_c6, check_c7, check_c8, check_c9, check_c10]


def run_checks(documents, rules):
    return [check(documents, rules) for check in CHECKS]


def findings_from(results):
    return [f for r in results for f in r.findings]
