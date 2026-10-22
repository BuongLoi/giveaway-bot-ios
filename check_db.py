import sqlite3
conn = sqlite3.connect("giveaways.db")
r = conn.execute("SELECT COUNT(*), COUNT(notified_at) FROM giveaways").fetchone()
print(f"Total: {r[0]}, Notified: {r[1]}")
rows = conn.execute("SELECT source, COUNT(*) FROM giveaways GROUP BY source ORDER BY COUNT(*) DESC").fetchall()
for s, n in rows:
    print(f"  {s}: {n}")
conn.close()
