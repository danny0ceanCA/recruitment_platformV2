from career_platform.app import app, db, Staff

# Simple migration script to populate new Staff columns from existing data
# Run with `python scripts/migrate_staff_details.py`

with app.app_context():
    for staff in Staff.query.all():
        # Populate first and last name from the existing name field if missing
        if not staff.first_name and staff.name:
            parts = staff.name.split(None, 1)
            staff.first_name = parts[0]
            if len(parts) > 1:
                staff.last_name = parts[1]
        if not staff.email:
            staff.email = f"{staff.username}@example.com"
    db.session.commit()
    print("Migration completed")
