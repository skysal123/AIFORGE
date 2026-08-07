import sqlite3

conn = sqlite3.connect("aiforge.db")
cursor = conn.cursor()

cursor.execute("SELECT * FROM enquiries LIMIT 10")
rows = cursor.fetchall()

for row in rows:
    print(row)