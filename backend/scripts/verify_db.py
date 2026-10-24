import psycopg

conn = psycopg.connect("postgresql://rag_user:rag_password@localhost:5432/rag_db")
cur = conn.cursor()

# Check tables
cur.execute("""
    SELECT table_name 
    FROM information_schema.tables 
    WHERE table_schema = 'public' 
    ORDER BY table_name;
""")
tables = [row[0] for row in cur.fetchall()]
print("Tables in rag_db:")
for t in tables:
    print(f"  - {t}")

# Check enums
cur.execute("""
    SELECT typname, enumlabel 
    FROM pg_enum e 
    JOIN pg_type t ON e.enumtypid = t.oid 
    ORDER BY typname, enumsortorder;
""")
enums = cur.fetchall()
print("\nCustom PostgreSQL Enums:")
for typ, label in enums:
    print(f"  - {typ}: {label}")

# Check foreign keys
cur.execute("""
    SELECT tc.table_name, kcu.column_name, ccu.table_name AS foreign_table, ccu.column_name AS foreign_col
    FROM information_schema.table_constraints AS tc 
    JOIN information_schema.key_column_usage AS kcu ON tc.constraint_name = kcu.constraint_name 
    JOIN information_schema.constraint_column_usage AS ccu ON ccu.constraint_name = tc.constraint_name 
    WHERE tc.constraint_type = 'FOREIGN KEY'
    ORDER BY tc.table_name;
""")
fks = cur.fetchall()
print("\nForeign Key Constraints:")
for tbl, col, ftbl, fcol in fks:
    print(f"  - {tbl}.{col} -> {ftbl}.{fcol}")

conn.close()
