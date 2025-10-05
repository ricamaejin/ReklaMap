import json
from sqlalchemy import text
from backend.app import app
from backend.database.db import db

"""
Migration: Overlapping table schema alignment
- q1: JSON (pairs) -> VARCHAR(200) CSV of current_status
- q2: VARCHAR(80) (current_status) -> JSON (pairs)
- q6: JSON -> VARCHAR(50)

This script:
1) Adds new columns q1_new (VARCHAR), q2_new (JSON), q6_new (VARCHAR)
2) Copies/transforms data row-by-row
3) Drops old columns and renames _new columns
Run once. Make a backup before running in production.
"""

def column_exists(engine, table, column):
    sql = text(
        """
        SELECT COUNT(*) FROM information_schema.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = :table AND COLUMN_NAME = :column
        """
    )
    res = engine.execute(sql, {"table": table, "column": column}).scalar()
    return res and int(res) > 0


def run_migration():
    with app.app_context():
        engine = db.engine
        conn = engine.connect()
        trans = conn.begin()
        try:
            # 1) Add new columns if not present
            adds = []
            if not column_exists(engine, "overlapping", "q1_new"):
                adds.append("ADD COLUMN q1_new VARCHAR(200) NULL")
            if not column_exists(engine, "overlapping", "q2_new"):
                adds.append("ADD COLUMN q2_new JSON NULL")
            if not column_exists(engine, "overlapping", "q6_new"):
                adds.append("ADD COLUMN q6_new VARCHAR(50) NULL")
            if adds:
                conn.execute(text(f"ALTER TABLE overlapping {', '.join(adds)}"))

            # 2) Select existing rows and transform
            rows = conn.execute(text("SELECT overlapping_id, q1, q2, q6 FROM overlapping")).mappings().all()
            for r in rows:
                oid = r["overlapping_id"]
                q1_old = r["q1"]  # JSON (pairs)
                q2_old = r["q2"]  # CSV current_status
                q6_old = r["q6"]  # JSON or string

                # q1_new: CSV from q2_old
                q1_new = (q2_old or "").strip() if q2_old else ""

                # q2_new: JSON from q1_old
                q2_new = []
                if q1_old:
                    try:
                        if isinstance(q1_old, (str, bytes)):
                            q2_new = json.loads(q1_old)
                        else:
                            # already a Python object from JSON column
                            q2_new = q1_old
                        if not isinstance(q2_new, list):
                            q2_new = []
                    except Exception:
                        q2_new = []

                # q6_new: simple string value
                if q6_old is None:
                    q6_new = None
                else:
                    try:
                        if isinstance(q6_old, (dict, list)):
                            q6_new = None
                        elif isinstance(q6_old, (str, bytes)):
                            q6_new = q6_old if q6_old else None
                        else:
                            q6_new = str(q6_old)
                    except Exception:
                        q6_new = None

                conn.execute(
                    text("UPDATE overlapping SET q1_new=:q1_new, q2_new=:q2_new, q6_new=:q6_new WHERE overlapping_id=:oid"),
                    {"q1_new": q1_new, "q2_new": json.dumps(q2_new), "q6_new": q6_new, "oid": oid},
                )

            # 3) Swap columns
            # Drop old if exist
            existing_cols = conn.execute(text("""
                SELECT COLUMN_NAME FROM information_schema.COLUMNS
                WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'overlapping'
            """)).fetchall()
            existing_cols = {c[0] for c in existing_cols}

            if "q1" in existing_cols:
                conn.execute(text("ALTER TABLE overlapping DROP COLUMN q1"))
            if "q2" in existing_cols:
                conn.execute(text("ALTER TABLE overlapping DROP COLUMN q2"))
            if "q6" in existing_cols:
                conn.execute(text("ALTER TABLE overlapping DROP COLUMN q6"))

            # Rename new to original names
            conn.execute(text("ALTER TABLE overlapping CHANGE COLUMN q1_new q1 VARCHAR(200) NULL"))
            conn.execute(text("ALTER TABLE overlapping CHANGE COLUMN q2_new q2 JSON NULL"))
            conn.execute(text("ALTER TABLE overlapping CHANGE COLUMN q6_new q6 VARCHAR(50) NULL"))

            trans.commit()
            print("Migration completed successfully.")
        except Exception as e:
            trans.rollback()
            print(f"Migration failed: {e}")
            raise


if __name__ == "__main__":
    run_migration()
