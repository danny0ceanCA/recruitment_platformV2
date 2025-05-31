from career_platform.app import app, db, Staff
from sqlalchemy import or_
import sys


def promote(identifier: str) -> None:
    """Promote a staff user to admin by username or email."""
    with app.app_context():
        user = Staff.query.filter(
            or_(Staff.username == identifier, Staff.email == identifier)
        ).first()
        if not user:
            print(f"User '{identifier}' not found")
            return
        if user.is_admin:
            print(f"User '{identifier}' is already an admin")
            return
        user.is_admin = True
        db.session.commit()
        print(f"Promoted '{identifier}' to admin")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python scripts/promote_admin.py <username-or-email>")
        sys.exit(1)
    promote(sys.argv[1])
