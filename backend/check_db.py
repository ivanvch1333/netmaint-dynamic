import psycopg2

conn = psycopg2.connect("postgresql://postgres:macaraxd@localhost:5432/mantenimiento_nodos")
cur = conn.cursor()

cur.execute("SELECT column_name FROM information_schema.columns WHERE table_name = 'usuarios' ORDER BY column_name;")
print("=== COLUMNAS EN usuarios ===")
for row in cur.fetchall():
    print(" -", row[0])

cur.execute("SELECT column_name FROM information_schema.columns WHERE table_name = 'reportes_mantenimiento' ORDER BY column_name;")
print("=== COLUMNAS EN reportes_mantenimiento ===")
for row in cur.fetchall():
    print(" -", row[0])

cur.execute("SELECT table_name FROM information_schema.tables WHERE table_schema='public' ORDER BY table_name;")
print("=== TABLAS EXISTENTES ===")
for row in cur.fetchall():
    print(" -", row[0])

cur.close()
conn.close()
print("DONE")
