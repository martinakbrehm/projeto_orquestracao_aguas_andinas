"""
Aplica as mudanças nas tabelas respostas e tabela_macros_aa:
  - Atualiza todas as mensagens e status de respostas (ids 1-7)
  - Insere ids 6 e 7 se não existirem
  - Altera ENUM de tabela_macros_aa.status para ('pendente','processando','telefone_validado','telefone_nao_validado')
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import pymysql
from config import db_aguas_andinas

RESPOSTAS = [
    (1, 'Sucesso com telefone e e-mail',  'telefone_validado'),
    (2, 'Sucesso sem dados',               'telefone_nao_validado'),
    (3, 'Usuário já registrado',           'telefone_nao_validado'),
    (4, 'Falha de conexão / API',         'telefone_nao_validado'),
    (5, 'Aguardando processamento',       'telefone_nao_validado'),
    (6, 'Sucesso apenas com telefone',    'telefone_validado'),
    (7, 'Sucesso apenas com e-mail',      'telefone_nao_validado'),
]

def main():
    conn = pymysql.connect(**db_aguas_andinas(autocommit=False))
    try:
        with conn.cursor() as cur:
            # Upsert respostas
            for rid, msg, status in RESPOSTAS:
                cur.execute(
                    "INSERT INTO respostas (id, mensagem, status) VALUES (%s,%s,%s) "
                    "ON DUPLICATE KEY UPDATE mensagem=VALUES(mensagem), status=VALUES(status)",
                    (rid, msg, status)
                )
                print(f"  resposta id={rid}: OK")

            # Altera ENUM de status em tabela_macros_aa
            cur.execute("""
                ALTER TABLE tabela_macros_aa
                MODIFY COLUMN status
                ENUM('pendente','processando','telefone_validado','telefone_nao_validado')
                NOT NULL DEFAULT 'pendente'
            """)
            print("  ALTER tabela_macros_aa.status: OK")

        conn.commit()
        print("\nMigração concluída.")
    except Exception as ex:
        conn.rollback()
        print(f"\n[ERRO] {ex}")
        sys.exit(1)
    finally:
        conn.close()

if __name__ == "__main__":
    main()
