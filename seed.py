"""
seed.py
-------
Run ONCE when deploying to a fresh database:

    python seed.py

Creates all tables and the first Super Master Admin account, using the
credentials from your .env file (SUPER_ADMIN_SEED_USERNAME /
SUPER_ADMIN_SEED_PASSWORD). Change that password immediately after first
login — the app will force a reset automatically (must_reset_password).
"""

import os
from dotenv import load_dotenv

from database import init_db, get_session, User, UserRole
from auth import hash_password

load_dotenv()


def run():
    init_db()
    username = os.getenv("SUPER_ADMIN_SEED_USERNAME", "super_admin")
    password = os.getenv("SUPER_ADMIN_SEED_PASSWORD", "ChangeMe_On_First_Login!")

    with get_session() as db:
        existing = db.query(User).filter(
            User.username == username, 
            User.role == UserRole.SUPER_MASTER_ADMIN
        ).first()

        if existing:
            existing.password_hash = hash_password(password)
            db.commit()
            print(f"✅ Super Master Admin '{username}' password successfully updated!")
            return

        admin = User(
            factory_id=None,
            username=username,
            full_name="Super Master Admin",
            role=UserRole.SUPER_MASTER_ADMIN,
            password_hash=hash_password(password),
            must_reset_password=True,
        )
        db.add(admin)
        db.commit()
        print(f"✅ Tables created. Super Master Admin '{username}' created.")
        print("   Log in with this account, then IMMEDIATELY change the password when prompted.")


if __name__ == "__main__":
    run()