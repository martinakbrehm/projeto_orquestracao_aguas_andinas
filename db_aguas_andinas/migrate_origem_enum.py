"""
migrate_origem_enum.py
Altera o ENUM da coluna `origem` nas tabelas telefones e emails:
  ANTES: ENUM('enriquecimento','extraido_api')
  DEPOIS: ENUM('enriquecimento','validado')

Também converte quaisquer registros existentes com origem='extraido_api'
para origem='validado' antes de alterar o ENUM.

Uso:
    python db_aguas_andinas/migrate_origem_enum.py
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import pymysql
from config import db_aguas_andinas

STEPS = [
    # 1. Converte valores existentes antes de mudar o ENUM
    ("telefones", "UPDATE telefones SET origem='validado' WHERE origem='extraido_api'"),
    ("emails",    "UPDATE emails    SET origem='validado' WHERE origem='extraido_api'"),
    # 2. Altera o ENUM da coluna origem em cada tabela
    ("telefones ALTER", """
        ALTER TABLE telefones
        MODIFY COLUMN origem ENUM('enriquecimento','validado') NOT NULL DEFAULT 'enriquecimento'
    """),
    ("emails ALTER", """
        ALTER TABLE emails
        MODIFY COLUMN origem ENUM('enriquecimento','validado') NOT NULL DEFAULT 'enriquecimento'
    """),
]

def main():
    conn = pymysql.connect(**db_aguas_andinas(autocommit=False))
    try:
        for label, sql in STEPS:
            print(f"  [{label}] ...", end=" ", flush=True)
            with conn.cursor() as cur:
                cur.execute(sql.strip())
                print(f"OK (rows affected: {cur.rowcount})")
        conn.commit()
        print("\nMigração concluída com sucesso.")
    except Exception as ex:
        conn.rollback()
        print(f"\n[ERRO] {ex}")
        sys.exit(1)
    finally:
        conn.close()

if __name__ == "__main__":
    main()
