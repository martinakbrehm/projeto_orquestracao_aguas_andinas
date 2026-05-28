"""
migrate_unique_macros_aa.py
===========================
Adiciona UNIQUE KEY em tabela_macros_aa.cliente_id para permitir
INSERT IGNORE / ON DUPLICATE KEY UPDATE.
"""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from config import db_aguas_andinas
import pymysql

conn = pymysql.connect(**db_aguas_andinas(autocommit=True))
with conn.cursor() as cur:
    # Verifica se a chave já existe
    cur.execute("""
        SELECT COUNT(*) FROM information_schema.STATISTICS
        WHERE TABLE_SCHEMA = DATABASE()
          AND TABLE_NAME   = 'tabela_macros_aa'
          AND INDEX_NAME   = 'uk_aa_macros_cliente'
    """)
    if cur.fetchone()[0] == 0:
        print("Adicionando UNIQUE KEY uk_aa_macros_cliente (cliente_id)...")
        cur.execute("""
            ALTER TABLE tabela_macros_aa
            ADD UNIQUE KEY uk_aa_macros_cliente (cliente_id)
        """)
        print("  OK")
    else:
        print("  UNIQUE KEY já existe — nada a fazer")
conn.close()
print("Concluído.")
