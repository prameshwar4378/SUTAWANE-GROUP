import sqlite3
from datetime import datetime, timezone

conn = sqlite3.connect('db.sqlite3')
cur = conn.cursor()

tables = [r[0] for r in cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' AND name NOT LIKE 'django_%' AND name NOT LIKE 'auth_%'").fetchall()]

for table in tables:
    cols = [c[1] for c in cur.execute(f"PRAGMA table_info('{table}')").fetchall()]
    date_cols = [c for c in cols if 'date' in c.lower() or 'at' in c.lower()]
    for c in date_cols:
        rows = cur.execute(f"SELECT {c} FROM '{table}' WHERE {c} IS NOT NULL LIMIT 5").fetchall()
        val_types = set(type(r[0]) for r in rows)
        sample = [r[0] for r in rows[:2]]
        print(f"{table}.{c}: types={val_types}, samples={sample}")
