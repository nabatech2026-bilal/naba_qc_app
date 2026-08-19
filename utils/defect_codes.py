"""
utils/defect_codes.py
----------------------
Default defect-code libraries transcribed from the client's own manual
registers (Cutting / Inline Stitching / Checking / Packing). These are
inserted once per new factory as a starting point — Main Admin /
Assistant Admin can add, rename, or deactivate codes afterwards from the
"Defect Code Management" screen (this is the "Dynamic Defects" feature).

Severity defaults are a reasonable starting classification
(Critical = fabric/garment unusable, Major = needs rework/re-stitch,
Minor = light cleaning/cosmetic) and are editable per factory.
"""

from database import Severity

DEFAULT_DEFECT_CODES = {
    "cutting": [
        ("Fabric Hole", Severity.CRITICAL),
        ("Knitting Line", Severity.MAJOR),
        ("Drop Needle", Severity.MAJOR),
        ("Shrinker Line", Severity.MAJOR),
        ("Oil Stain", Severity.MINOR),
        ("Ladder / Streaks", Severity.MAJOR),
        ("Slub", Severity.MINOR),
        ("Yarn Fly", Severity.MINOR),
        ("Stain", Severity.MINOR),
        ("Registration Out", Severity.MAJOR),
        ("Spot / Color Marks", Severity.MINOR),
        ("Dirt Mark", Severity.MINOR),
        ("Shaded Panel", Severity.MAJOR),
        ("Dyeing Patch", Severity.MAJOR),
        ("Softener Mark", Severity.MINOR),
        ("Missing Notches", Severity.MAJOR),
    ],
    "stitching": [
        ("Skip Stitch", Severity.MAJOR),
        ("Broken Stitch", Severity.MAJOR),
        ("Open Seam", Severity.CRITICAL),
        ("Uneven Stitch", Severity.MINOR),
        ("Loose Stitch", Severity.MAJOR),
        ("Puckering / Pleat", Severity.MINOR),
        ("Overlapping", Severity.MINOR),
        ("Raw Edge", Severity.MAJOR),
        ("Needle Hole", Severity.MAJOR),
        ("Insecure Stitch", Severity.MAJOR),
        ("Oil Stain", Severity.MINOR),
        ("Stain", Severity.MINOR),
        ("Damage Button Hole", Severity.MAJOR),
        ("Uneven Button Placement", Severity.MINOR),
        ("Label Damage / Wrong / Missing", Severity.MAJOR),
        ("Short SPI", Severity.MINOR),
        ("Wrong Side Hem", Severity.MAJOR),
        ("Bowing", Severity.MINOR),
    ],
    "checking": [
        ("Drop Needle", Severity.MAJOR),
        ("Yarn Fly", Severity.MINOR),
        ("Hole / Damage", Severity.CRITICAL),
        ("Open Seam", Severity.CRITICAL),
        ("Broken Stitch", Severity.MAJOR),
        ("Skip Stitch", Severity.MAJOR),
        ("Puckering", Severity.MINOR),
        ("Pleat", Severity.MINOR),
        ("Missing / Wrong / Insecure Label", Severity.MAJOR),
        ("Overlapping", Severity.MINOR),
        ("Raw Edge", Severity.MAJOR),
        ("Uneven Stitch", Severity.MINOR),
        ("Loose Stitch", Severity.MAJOR),
        ("Needle Holes", Severity.MAJOR),
        ("Mis Printing", Severity.MAJOR),
        ("Shade Variation", Severity.MAJOR),
        ("Registration Out", Severity.MAJOR),
        ("Run Off Stitch", Severity.MAJOR),
        ("Stain", Severity.MINOR),
        ("Dirt Mark", Severity.MINOR),
        ("Oil Stain", Severity.MINOR),
        ("Uncut Thread", Severity.MINOR),
        ("Wrong Size", Severity.CRITICAL),
        ("Uncut Elastic", Severity.MAJOR),
        ("Damage Button Hole", Severity.MAJOR),
        ("Touching", Severity.MINOR),
        ("Wrong Direction", Severity.MAJOR),
        ("Missing / Insecure Button", Severity.MAJOR),
        ("Bad Stitch", Severity.MAJOR),
        ("Double Stitch", Severity.MINOR),
        ("Other", Severity.MINOR),
    ],
    "packing": [
        ("Fabric Hole", Severity.CRITICAL),
        ("Yarn Fly", Severity.MINOR),
        ("Ladder / Streak", Severity.MAJOR),
        ("Knitting Line", Severity.MAJOR),
        ("Misprint", Severity.MAJOR),
        ("Miss / Double Pick", Severity.MAJOR),
        ("Registration Out", Severity.MAJOR),
        ("Open Seam", Severity.CRITICAL),
        ("Skip Stitch", Severity.MAJOR),
        ("Broken Stitch", Severity.MAJOR),
        ("Raw Edge", Severity.MAJOR),
        ("Mix Size", Severity.CRITICAL),
        ("Oil Stain", Severity.MINOR),
        ("Stain", Severity.MINOR),
        ("Dirt Mark", Severity.MINOR),
        ("Needle Holes", Severity.MAJOR),
        ("Uncut Thread", Severity.MINOR),
        ("Uneven Fold", Severity.MINOR),
        ("Loose Packing", Severity.MINOR),
        ("Barcode Missing / Wrong / Damage", Severity.MAJOR),
        ("Barcode Reverse / Slant", Severity.MINOR),
        ("Safety Sticker Missing / Wrong / Damage", Severity.MAJOR),
        ("Safety Sticker Slant / Reverse", Severity.MINOR),
        ("Size Sticker Missing / Wrong / Damage", Severity.MAJOR),
        ("Size Sticker Slant / Reverse", Severity.MINOR),
        ("Damage Polybag", Severity.MINOR),
        ("Inlay Card Damage / Wrong", Severity.MAJOR),
        ("Inlay Card Misprint / Registration Out", Severity.MAJOR),
        ("Dirty Polybag", Severity.MINOR),
        ("Loose Thread", Severity.MINOR),
        ("Damage Stiffener Sheet", Severity.MINOR),
        ("Fluff", Severity.MINOR),
        ("Wrong Size Polybag", Severity.MAJOR),
        ("Shade Within a Set", Severity.MAJOR),
        ("Wrong Assortment", Severity.CRITICAL),
        ("Focal / Motive Point Out", Severity.MINOR),
    ],
}


def _next_code(index: int) -> str:
    """A, B, ... Z, AA, AB, ... matching the register's lettering style."""
    letters = ""
    index += 1
    while index > 0:
        index, rem = divmod(index - 1, 26)
        letters = chr(65 + rem) + letters
    return letters


def seed_defect_codes_for_factory(db, factory_id: int):
    """Insert the default library for a brand-new factory. Call once at factory setup."""
    from database import DefectCode
    for department, items in DEFAULT_DEFECT_CODES.items():
        for i, (label, severity) in enumerate(items):
            db.add(DefectCode(
                factory_id=factory_id,
                department=department,
                code=_next_code(i),
                label=label,
                default_severity=severity,
            ))
