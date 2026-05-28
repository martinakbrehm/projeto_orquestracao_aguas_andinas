"""Script de diagnóstico rápido para o import de emails."""
import sys, csv
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from config import db_aguas_andinas
import pymysql

EMAIL_FILE = ROOT / "dados" / "bases" / "ENTREGA CORREOv.txt"
ENCODING = "latin-1"

# 1. Testa conexão e staging
print("=== Conectando ao banco ===")
cfg = db_aguas_andinas(autocommit=False, read_timeout=7200, write_timeout=7200)
print("Config OK:", {k: v for k, v in cfg.items() if k != 'password'})
conn = pymysql.connect(**cfg)
print("Conexão OK")

with conn.cursor() as cur:
    cur.execute("SET SESSION innodb_lock_wait_timeout = 300")
    cur.execute("SELECT id, filename FROM staging_imports ORDER BY id DESC LIMIT 3")
    print("staging_imports:", cur.fetchall())

# 2. Lê 10 linhas do arquivo de email
print("\n=== Primeiras 10 linhas do arquivo de emails ===")
with open(EMAIL_FILE, encoding=ENCODING, newline="") as f:
    reader = csv.DictReader(f, delimiter=";")
    for i, row in enumerate(reader):
        if i >= 10:
            break
        print(dict(row))

# 3. Testa INSERT de 1 email
print("\n=== Teste de INSERT ===")
with conn.cursor() as cur:
    cur.execute("SELECT id FROM clientes LIMIT 1")
    cid = cur.fetchone()[0]
    print(f"  cliente_id de teste: {cid}")
    sql = "INSERT IGNORE INTO emails (cliente_id, endereco, origem, staging_id) VALUES (%s, %s, 'enriquecimento', %s)"
    cur.execute(sql, (cid, "teste@diagnostico.com", 1))
    print(f"  rowcount: {cur.rowcount}")
    conn.rollback()
    print("  rollback OK")

print("\nDiagnóstico concluído OK")
conn.close()
