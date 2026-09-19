"""
fix_department_enum.py
-------------------------
One-time migration: Postgres stores the `department` column as a native
ENUM type (created the first time the app ran, with only cutting /
stitching / checking / packing as valid values). Adding "knitting" and
"dyeing" to the Python Department enum does NOT automatically add them
to that existing Postgres type — the database has to be told explicitly
via ALTER TYPE. Without this, any attempt to save a Knitting or Dyeing
report (or add their defect codes) fails with an "invalid input value
for enum" error.

Run this BEFORE migrate_add_knitting_dyeing.py.

Safe to run more than once (uses ADD VALUE IF NOT EXISTS).

Usage:
    python fix_department_enum.py
"""

from sqlalchemy import text
from database import engine

NEW_VALUES = ["knitting", "dyeing"]


def _get_enum_type_name(conn) -> str | None:
    """Finds the actual Postgres enum type name backing inspection_reports.department,
    whatever SQLAlchemy happened to name it — no guessing required."""
    result = conn.execute(text("""
        SELECT udt_name FROM information_schema.columns
        WHERE table_name = 'inspection_reports' AND column_name = 'department'
    """)).fetchone()
    return result[0] if result else None


def run():
    # AUTOCOMMIT is required: ALTER TYPE ... ADD VALUE cannot run inside a
    # regular open transaction block in Postgres.
    with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
        type_name = _get_enum_type_name(conn)
        if not type_name:
            print("❌ Could not find the department column — has seed.py been run on this database?")
            return
        print(f"ℹ️  Found Postgres enum type: {type_name}")

        for value in NEW_VALUES:
            conn.execute(text(f"ALTER TYPE {type_name} ADD VALUE IF NOT EXISTS '{value}'"))
            print(f"✅ Enum now accepts: {value}")

    print("✅ Enum migration complete. Now run: python migrate_add_knitting_dyeing.py")


if __name__ == "__main__":
    run()
