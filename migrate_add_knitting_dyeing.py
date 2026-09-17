"""
migrate_add_knitting_dyeing.py
--------------------------------
One-time migration: seeds the default Knitting and Dyeing/Processing
defect-code libraries for every EXISTING factory. New factories created
after this update already get these automatically (via
seed_defect_codes_for_factory), but factories created before these two
departments existed need this run once so their dropdowns aren't empty.

Safe to run more than once — it skips a department for a factory if
defect codes for it already exist there.

Usage:
    python migrate_add_knitting_dyeing.py
"""

from database import get_session, Factory, DefectCode
from utils.defect_codes import DEFAULT_DEFECT_CODES, _next_code

NEW_DEPARTMENTS = ["knitting", "dyeing"]


def run():
    with get_session() as db:
        factories = db.query(Factory).all()
        for factory in factories:
            for department in NEW_DEPARTMENTS:
                existing = db.query(DefectCode).filter(
                    DefectCode.factory_id == factory.id, DefectCode.department == department
                ).first()
                if existing:
                    print(f"ℹ️  Factory '{factory.name}': '{department}' defect codes already exist — skipped.")
                    continue
                items = DEFAULT_DEFECT_CODES.get(department, [])
                for i, (label, severity) in enumerate(items):
                    db.add(DefectCode(
                        factory_id=factory.id,
                        department=department,
                        code=_next_code(i),
                        label=label,
                        default_severity=severity,
                    ))
                print(f"✅ Factory '{factory.name}': added {len(items)} '{department}' defect codes.")
        db.commit()
    print("✅ Migration complete.")


if __name__ == "__main__":
    run()
