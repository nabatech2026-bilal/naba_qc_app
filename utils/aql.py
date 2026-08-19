"""
utils/aql.py
------------
Simplified AQL (Acceptable Quality Limit) pass/fail logic, based on the
General Inspection Level II single-sampling table (ANSI/ASQ Z1.4 /
ISO 2859-1) — the same standard referenced on the client's registers
("AQL Level: MAJ 2.5, Min 4.0").

This is a *simplified* lookup covering the lot-size ranges typical in
garment QC. For legal/contractual disputes a factory should still keep a
copy of the full published Z1.4 tables; this module is meant to automate
the everyday floor decision exactly like the paper register does.
"""

from dataclasses import dataclass

# (lot_size_min, lot_size_max, sample_size, code_letter)
SAMPLE_SIZE_TABLE = [
    (2, 8, 2, "A"),
    (9, 15, 3, "B"),
    (16, 25, 5, "C"),
    (26, 50, 8, "D"),
    (51, 90, 13, "E"),
    (91, 150, 20, "F"),
    (151, 280, 32, "G"),
    (281, 500, 50, "H"),
    (501, 1200, 80, "J"),
    (1201, 3200, 125, "K"),
    (3201, 10000, 200, "L"),
    (10001, 35000, 315, "M"),
    (35001, 150000, 500, "N"),
]

# Accept (Ac) / Reject (Re) numbers for common AQL levels at each sample size
# code letter, General Inspection Level II, single sampling normal plan.
# Format: {code_letter: {aql_value: (Ac, Re)}}
AC_RE_TABLE = {
    "A": {1.5: (0, 1), 2.5: (0, 1), 4.0: (0, 1)},
    "B": {1.5: (0, 1), 2.5: (0, 1), 4.0: (0, 1)},
    "C": {1.5: (0, 1), 2.5: (1, 2), 4.0: (1, 2)},
    "D": {1.5: (1, 2), 2.5: (1, 2), 4.0: (2, 3)},
    "E": {1.5: (1, 2), 2.5: (2, 3), 4.0: (3, 4)},
    "F": {1.5: (2, 3), 2.5: (3, 4), 4.0: (5, 6)},
    "G": {1.5: (3, 4), 2.5: (5, 6), 4.0: (7, 8)},
    "H": {1.5: (5, 6), 2.5: (7, 8), 4.0: (10, 11)},
    "J": {1.5: (7, 8), 2.5: (10, 11), 4.0: (14, 15)},
    "K": {1.5: (10, 11), 2.5: (14, 15), 4.0: (21, 22)},
    "L": {1.5: (14, 15), 2.5: (21, 22), 4.0: (21, 22)},
    "M": {1.5: (21, 22), 2.5: (21, 22), 4.0: (21, 22)},
    "N": {1.5: (21, 22), 2.5: (21, 22), 4.0: (21, 22)},
}


@dataclass
class AQLResult:
    sample_size: int
    code_letter: str
    accept_number: int
    reject_number: int
    major_defects_found: int
    minor_defects_found: int
    status: str          # "PASS" or "FAIL"
    reason: str


def get_sample_size(lot_size: int) -> tuple[int, str]:
    for lo, hi, size, code in SAMPLE_SIZE_TABLE:
        if lo <= lot_size <= hi:
            return size, code
    # lot larger than table range -> use largest bracket
    return SAMPLE_SIZE_TABLE[-1][2], SAMPLE_SIZE_TABLE[-1][3]


def evaluate_lot(lot_size: int, major_defects: int, minor_defects: int,
                  major_aql: float = 2.5, minor_aql: float = 4.0) -> AQLResult:
    """
    Mirrors the register's "AQL Level: MAJ 2.5, Min 4.0" + AC/RE columns.
    A lot fails if EITHER the major or minor defect count exceeds its
    respective reject number.
    """
    sample_size, code_letter = get_sample_size(lot_size)
    major_table = AC_RE_TABLE.get(code_letter, {})
    minor_table = AC_RE_TABLE.get(code_letter, {})

    ac_major, re_major = major_table.get(major_aql, (0, 1))
    ac_minor, re_minor = minor_table.get(minor_aql, (0, 1))

    major_fail = major_defects >= re_major
    minor_fail = minor_defects >= re_minor

    if major_fail or minor_fail:
        status = "FAIL"
        reasons = []
        if major_fail:
            reasons.append(f"Major defects {major_defects} >= reject {re_major}")
        if minor_fail:
            reasons.append(f"Minor defects {minor_defects} >= reject {re_minor}")
        reason = "; ".join(reasons)
    else:
        status = "PASS"
        reason = f"Major {major_defects} <= Ac {ac_major}, Minor {minor_defects} <= Ac {ac_minor}"

    return AQLResult(
        sample_size=sample_size,
        code_letter=code_letter,
        accept_number=ac_major,
        reject_number=re_major,
        major_defects_found=major_defects,
        minor_defects_found=minor_defects,
        status=status,
        reason=reason,
    )


def defective_percentage(total_inspected: int, total_defects: int) -> float:
    if total_inspected <= 0:
        return 0.0
    return round((total_defects / total_inspected) * 100, 2)
