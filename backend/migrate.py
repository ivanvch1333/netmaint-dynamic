import psycopg2

conn = psycopg2.connect("postgresql://postgres:macaraxd@localhost:5432/mantenimiento_nodos")
conn.autocommit = True
cur = conn.cursor()

migrations = []

# --- Tabla: usuarios ---

# Verificar si ya existe intentos_fallidos
cur.execute("""
    SELECT column_name FROM information_schema.columns
    WHERE table_name = 'usuarios' AND column_name = 'intentos_fallidos';
""")
if not cur.fetchone():
    cur.execute("ALTER TABLE usuarios ADD COLUMN intentos_fallidos INTEGER NOT NULL DEFAULT 0;")
    migrations.append("  [OK] usuarios.intentos_fallidos ADDED")
else:
    migrations.append("  [--] usuarios.intentos_fallidos already exists, skipped")

# Verificar si ya existe bloqueado_hasta
cur.execute("""
    SELECT column_name FROM information_schema.columns
    WHERE table_name = 'usuarios' AND column_name = 'bloqueado_hasta';
""")
if not cur.fetchone():
    cur.execute("ALTER TABLE usuarios ADD COLUMN bloqueado_hasta TIMESTAMP NULL;")
    migrations.append("  [OK] usuarios.bloqueado_hasta ADDED")
else:
    migrations.append("  [--] usuarios.bloqueado_hasta already exists, skipped")

# --- Tabla: reportes_mantenimiento ---

# Verificar si ya existe firma_tecnico_url
cur.execute("""
    SELECT column_name FROM information_schema.columns
    WHERE table_name = 'reportes_mantenimiento' AND column_name = 'firma_tecnico_url';
""")
if not cur.fetchone():
    cur.execute("ALTER TABLE reportes_mantenimiento ADD COLUMN firma_tecnico_url VARCHAR(255) NULL;")
    migrations.append("  [OK] reportes_mantenimiento.firma_tecnico_url ADDED")
else:
    migrations.append("  [--] reportes_mantenimiento.firma_tecnico_url already exists, skipped")

# Verificar si ya existe recomendaciones
cur.execute("""
    SELECT column_name FROM information_schema.columns
    WHERE table_name = 'reportes_mantenimiento' AND column_name = 'recomendaciones';
""")
if not cur.fetchone():
    cur.execute("ALTER TABLE reportes_mantenimiento ADD COLUMN recomendaciones TEXT NULL;")
    migrations.append("  [OK] reportes_mantenimiento.recomendaciones ADDED")
else:
    migrations.append("  [--] reportes_mantenimiento.recomendaciones already exists, skipped")

# --- Nuevas columnas: fecha_inicio y fecha_cierre (TIMESTAMP) en ordenes_trabajo ---
cur.execute("""
    SELECT column_name FROM information_schema.columns
    WHERE table_name = 'ordenes_trabajo' AND column_name = 'fecha_inicio';
""")
if not cur.fetchone():
    cur.execute("ALTER TABLE ordenes_trabajo ADD COLUMN fecha_inicio TIMESTAMP NULL;")
    migrations.append("  [OK] ordenes_trabajo.fecha_inicio ADDED")
else:
    migrations.append("  [--] ordenes_trabajo.fecha_inicio already exists, skipped")

# Cambiar tipo de fecha_cierre a TIMESTAMP en ordenes_trabajo
cur.execute("ALTER TABLE ordenes_trabajo ALTER COLUMN fecha_cierre TYPE TIMESTAMP USING fecha_cierre::timestamp;")
migrations.append("  [OK] ordenes_trabajo.fecha_cierre ALTERED to TIMESTAMP")

# --- Nuevas columnas en reportes_mantenimiento ---
for col, col_type in [("latitud_tecnico", "DOUBLE PRECISION"), ("longitud_tecnico", "DOUBLE PRECISION"), ("ingeniero_autorizador", "VARCHAR(150)")]:
    cur.execute("""
        SELECT column_name FROM information_schema.columns
        WHERE table_name = 'reportes_mantenimiento' AND column_name = %s;
    """, (col,))
    if not cur.fetchone():
        cur.execute("ALTER TABLE reportes_mantenimiento ADD COLUMN {} {} NULL;".format(col, col_type))
        migrations.append("  [OK] reportes_mantenimiento.{} ADDED".format(col))
    else:
        migrations.append("  [--] reportes_mantenimiento.{} already exists, skipped".format(col))

# --- Nueva columna en configuracion_empresa ---
cur.execute("""
    SELECT column_name FROM information_schema.columns
    WHERE table_name = 'configuracion_empresa' AND column_name = 'url_footer_local';
""")
if not cur.fetchone():
    cur.execute("ALTER TABLE configuracion_empresa ADD COLUMN url_footer_local VARCHAR(255) NULL;")
    migrations.append("  [OK] configuracion_empresa.url_footer_local ADDED")
else:
    migrations.append("  [--] configuracion_empresa.url_footer_local already exists, skipped")

cur.close()
conn.close()

print("=== MIGRACION COMPLETADA ===")
for m in migrations:
    print(m)
print("DONE")
