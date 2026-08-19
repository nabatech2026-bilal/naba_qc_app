"""
migrate_add_brand_week.py
---------------------------
One-time migration: adds the new `brand` and `week` columns to the
EXISTING inspection_reports table on Supabase (init_db() only creates
brand-new tables — it can't add columns to a table that already exists,
which is why this needed a separate script).

Safe to run more than once — it checks whether each column already
exists before trying to add it.

Usage:
    python migrate_add_brand_week.py
"""

from sqlalchemy import text
from database import engine

def run():
    with engine.connect() as conn:
        # Check which columns already exist so this script is safe to re-run.
        existing = conn.execute(text("""
            SELECT column_name FROM information_schema.columns
            WHERE table_name = 'inspection_reports'
        """)).fetchall()
        existing_cols = {row[0] for row in existing}

        if "brand" not in existing_cols:
            conn.execute(text("ALTER TABLE inspection_reports ADD COLUMN brand VARCHAR(50)"))
            print("✅ Added column: brand")
        else:
            print("ℹ️  Column 'brand' already exists — skipped.")

        if "week" not in existing_cols:
            conn.execute(text("ALTER TABLE inspection_reports ADD COLUMN week VARCHAR(20)"))
            print("✅ Added column: week")
        else:
            print("ℹ️  Column 'week' already exists — skipped.")

        conn.commit()
    print("✅ Migration complete. The article_master table (new) will be created automatically on next app run.")


if __name__ == "__main__":
    run()
