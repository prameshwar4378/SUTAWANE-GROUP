import sqlite3
from datetime import datetime, timezone

conn = sqlite3.connect('db.sqlite3')
cur = conn.cursor()

tables = [r[0] for r in cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' AND name NOT LIKE 'django_%' AND name NOT LIKE 'auth_%'").fetchall()]

total_converted = 0
for table in tables:
    cols = [c[1] for c in cur.execute(f"PRAGMA table_info('{table}')").fetchall()]
    date_cols = [c for c in cols if 'date' in c.lower() or 'at' in c.lower()]
    for c in date_cols:
        rows = cur.execute(f"SELECT id, {c} FROM '{table}' WHERE {c} IS NOT NULL").fetchall() if 'id' in cols else cur.execute(f"SELECT key, {c} FROM '{table}' WHERE {c} IS NOT NULL").fetchall()
        for pk, val in rows:
            if isinstance(val, int) and val > 10000000000:  # millisecond timestamp
                iso_str = datetime.fromtimestamp(val / 1000.0, tz=timezone.utc).strftime('%Y-%m-%d %H:%M:%S.%f')
                pk_col = 'id' if 'id' in cols else 'key'
                cur.execute(f"UPDATE '{table}' SET {c} = ? WHERE {pk_col} = ?", (iso_str, pk))
                total_converted += 1

conn.commit()
print(f"Successfully normalized {total_converted} timestamp values into ISO format in db.sqlite3!")
