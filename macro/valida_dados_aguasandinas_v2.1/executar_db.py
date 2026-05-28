"""
executar_db.py — Runner integrado ao banco de dados
=====================================================
Substitui o fluxo CSV:
  banco (pendente) → extrator AJAX → banco (telefone_validado / telefone_nao_validado)

Uso:
  python executar_db.py                    # processa lotes de 500 até zerar pendentes
  python executar_db.py --lotes 3          # processa no máximo 3 lotes
  python executar_db.py --tamanho 100      # lotes de 100 registros
  python executar_db.py --pausa 2          # pausa (s) entre requisições (default: 1)
  python executar_db.py --dry-run          # consulta a API mas não salva no banco

Execução a partir da raiz do projeto:
  python macro/valida_dados_aguasandinas_v2.1/executar_db.py
"""

import argparse
import sys
import time
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths — permite importar config.py (raiz) e core/ (pasta da macro)
# ---------------------------------------------------------------------------
_MACRO_DIR   = Path(__file__).parent
_PROJECT_DIR = _MACRO_DIR.parent.parent
sys.path.insert(0, str(_MACRO_DIR))     # para core/
sys.path.insert(0, str(_PROJECT_DIR))   # para config.py e etl/  (tem precedência)

import pymysql
from config import db_aguas_andinas
from core.extrator import Extrator
from etl.transformation.macro_aa.interpretar_resposta_aa import interpretar

SEP = "=" * 70


# ---------------------------------------------------------------------------
# SQL
# ---------------------------------------------------------------------------
SQL_BUSCAR_LOTE = """
    SELECT tm.id, tm.cliente_id, c.rut, c.dv
    FROM tabela_macros_aa tm
    JOIN clientes c ON c.id = tm.cliente_id
    WHERE tm.status = 'pendente'
    ORDER BY tm.id ASC
    LIMIT %s
    FOR UPDATE SKIP LOCKED
"""

SQL_MARCAR_PROCESSANDO = """
    UPDATE tabela_macros_aa SET status = 'processando'
    WHERE id IN ({placeholders})
"""

SQL_REVERTER_PENDENTE = """
    UPDATE tabela_macros_aa SET status = 'pendente'
    WHERE id IN ({placeholders})
"""

SQL_BULK_TEL = (
    "INSERT IGNORE INTO telefones (cliente_id, numero, origem) VALUES "
)

SQL_BULK_EMAIL = (
    "INSERT IGNORE INTO emails (cliente_id, endereco, origem) VALUES "
)

SQL_UPDATE_MACRO = """
    UPDATE tabela_macros_aa
    SET resposta_id = %s, status = %s, data_update = NOW()
    WHERE id = %s
"""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def conectar() -> pymysql.Connection:
    conn = pymysql.connect(**db_aguas_andinas(autocommit=False))
    with conn.cursor() as cur:
        cur.execute("SET SESSION innodb_lock_wait_timeout = 60")
    return conn


def _ids_placeholders(ids: list) -> str:
    return ",".join(["%s"] * len(ids))


def _bulk_insert(cur, base_sql: str, rows: list[tuple]) -> int:
    if not rows:
        return 0
    ph = ",".join(["(" + ",".join(["%s"] * len(rows[0])) + ")"] * len(rows))
    flat = [v for row in rows for v in row]
    cur.execute(base_sql + ph, flat)
    return cur.rowcount


# ---------------------------------------------------------------------------
# Core
# ---------------------------------------------------------------------------
def processar_lote(
    conn: pymysql.Connection,
    extrator: Extrator,
    tamanho: int,
    pausa: float,
    dry_run: bool,
) -> tuple[int, int]:
    """
    Busca um lote do banco, consulta a API para cada RUT e salva os resultados.
    Retorna (processados, erros_fatais).
    """
    with conn.cursor() as cur:
        cur.execute(SQL_BUSCAR_LOTE, (tamanho,))
        lote = cur.fetchall()

    if not lote:
        return 0, 0

    ids        = [r[0] for r in lote]
    total      = len(lote)
    print(f"  Lote: {total} registros (ids {ids[0]}…{ids[-1]})")

    if not dry_run:
        ph = _ids_placeholders(ids)
        with conn.cursor() as cur:
            cur.execute(SQL_MARCAR_PROCESSANDO.format(placeholders=ph), ids)
        conn.commit()

    tel_batch:    list[tuple] = []
    email_batch:  list[tuple] = []
    macro_batch:  list[tuple] = []   # (resposta_id, status, macro_id)
    erros_fatais  = 0

    for i, (macro_id, cliente_id, rut, dv) in enumerate(lote, start=1):
        try:
            resultado = extrator.consultar_rut(str(rut), str(dv or ""))
        except RuntimeError as e:
            # Falha de conexão/API após todas as tentativas
            print(f"  [ERRO FATAL] RUT {rut}: {e}")
            erros_fatais += 1
            resultado = {"telefone": "", "email": "", "sucesso": 0, "erro": str(e)}

        telefone = str(resultado.get("telefone") or "").strip()
        email    = str(resultado.get("email")    or "").strip()
        sucesso  = str(resultado.get("sucesso",  0))
        erro     = str(resultado.get("erro",     "") or "")

        resposta_id, novo_status = interpretar(sucesso, telefone, email, erro)

        print(f"  [{i:>3}/{total}] RUT {rut} -> {novo_status} tel={telefone!r} email={email!r}")

        if not dry_run:
            if telefone:
                tel_batch.append((cliente_id, telefone, "validado"))
            if email:
                email_batch.append((cliente_id, email, "validado"))
            macro_batch.append((resposta_id, novo_status, macro_id))

        if pausa > 0:
            time.sleep(pausa)

    if dry_run:
        print(f"  dry-run: {total} consultados, nenhum salvo.")
        return total, erros_fatais

    with conn.cursor() as cur:
        _bulk_insert(cur, SQL_BULK_TEL,   tel_batch)
        _bulk_insert(cur, SQL_BULK_EMAIL, email_batch)
        for resposta_id, novo_status, macro_id in macro_batch:
            cur.execute(SQL_UPDATE_MACRO, (resposta_id, novo_status, macro_id))
    conn.commit()

    ok = total - erros_fatais
    print(f"  Salvo: {ok} ok | {erros_fatais} erros fatais | tel={len(tel_batch)} email={len(email_batch)}")

    # Se todos falharam por conexão → sinaliza para o loop principal parar
    if erros_fatais == total:
        raise RuntimeError("Todos os registros do lote falharam. API pode estar indisponível.")

    return total, erros_fatais


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> None:
    parser = argparse.ArgumentParser(description="Macro Águas Andinas — modo banco de dados")
    parser.add_argument("--lotes",   type=int,   default=0,   help="Nº máximo de lotes (0 = sem limite)")
    parser.add_argument("--tamanho", type=int,   default=500, help="Registros por lote (default: 500)")
    parser.add_argument("--pausa",   type=float, default=1.0, help="Pausa (s) entre requisições (default: 1)")
    parser.add_argument("--dry-run", action="store_true",     help="Consulta API mas não salva no banco")
    args = parser.parse_args()

    print(SEP)
    print("Macro Águas Andinas — integração com banco de dados")
    print(f"Tamanho do lote : {args.tamanho}")
    print(f"Pausa           : {args.pausa}s")
    print(f"Dry-run         : {args.dry_run}")
    print(f"Máx. lotes      : {args.lotes or 'sem limite'}")
    print(SEP)

    extrator = Extrator()
    conn     = conectar()

    total_processados = 0
    total_erros       = 0
    lote_num          = 0

    try:
        while True:
            lote_num += 1
            print(f"\nLote #{lote_num}")

            processados, erros = processar_lote(
                conn, extrator,
                tamanho=args.tamanho,
                pausa=args.pausa,
                dry_run=args.dry_run,
            )

            if processados == 0:
                print("Nenhum registro pendente. Processamento concluído.")
                break

            total_processados += processados
            total_erros       += erros

            if args.lotes > 0 and lote_num >= args.lotes:
                print(f"Limite de {args.lotes} lote(s) atingido.")
                break

    except RuntimeError as e:
        print(f"\n[INTERROMPIDO] {e}")
        sys.exit(1)
    except KeyboardInterrupt:
        print("\n[INTERROMPIDO] Ctrl+C recebido.")
    finally:
        conn.close()

    print(f"\n{SEP}")
    print(f"Total processados : {total_processados}")
    print(f"Total erros fatais: {total_erros}")
    print(SEP)


if __name__ == "__main__":
    main()
