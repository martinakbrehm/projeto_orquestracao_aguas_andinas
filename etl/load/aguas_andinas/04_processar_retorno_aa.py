"""
04_processar_retorno_aa.py
==========================
ETAPA — Processa os CSVs resultado da macro Águas Andinas.

Responsabilidade:
  1. Lê um ou mais arquivos CSV de resultado da macro:
       macro/valida_dados_aguasandinas_v2.1/planilha/*_RESULTADO.csv
     Colunas esperadas: RUT;DV;TELEFONE_VALIDADO;EMAIL_VALIDADO;SUCESSO;ERRO
  2. Para cada linha, busca o cliente_id correspondente em `clientes`.
  3. Interpreta SUCESSO/TELEFONE_VALIDADO/EMAIL_VALIDADO/ERRO via
     interpretar_resposta_aa.interpretar() → (resposta_id, novo_status)
  4. Insere telefone/e-mail validado em `telefones`/`emails` (origem='validado'),
     se ainda não existirem para aquele cliente.
  5. Atualiza tabela_macros_aa:
       status      = novo_status
       resposta_id = resposta_id
       telefone_id / email_id  (FK para os registros inseridos)
     — usa UPDATE WHERE status IN ('pendente','processando')
       para não sobrescrever resultados já finalizados.
  6. Linhas com cliente_id desconhecido são ignoradas (logadas).

Fluxo de status em tabela_macros_aa:
  pendente/processando → telefone_validado | telefone_nao_validado | pendente (retry)

Uso:
    python etl/load/aguas_andinas/04_processar_retorno_aa.py
    python etl/load/aguas_andinas/04_processar_retorno_aa.py --dry-run
    python etl/load/aguas_andinas/04_processar_retorno_aa.py --arquivo macro/valida_dados_aguasandinas_v2.1/planilha/RESULTADO.csv
"""

import argparse
import csv
import sys
from pathlib import Path

import pymysql

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from config import db_aguas_andinas  # noqa: E402

sys.path.insert(0, str(ROOT / "etl" / "transformation" / "macro_aa"))
from interpretar_resposta_aa import interpretar  # noqa: E402

# ---------------------------------------------------------------------------
# Configuração
# ---------------------------------------------------------------------------
RESULTADO_DIR = ROOT / "macro" / "valida_dados_aguasandinas_v2.1" / "planilha"
BATCH_SIZE    = 500
SEP           = "=" * 70


# ---------------------------------------------------------------------------
# SQL  (bulk)
# ---------------------------------------------------------------------------

# Telefones: coluna 'numero'
SQL_BULK_TEL = (
    "INSERT IGNORE INTO telefones (cliente_id, numero, origem) VALUES "
)

# Emails: coluna 'endereco'
SQL_BULK_EMAIL = (
    "INSERT IGNORE INTO emails (cliente_id, endereco, origem) VALUES "
)

# tabela_macros_aa — INSERT com ON DUPLICATE KEY UPDATE
# UNIQUE KEY uk_aa_macros_cliente(cliente_id) já existe após migrate_unique_macros_aa.py
SQL_BULK_MACRO = (
    "INSERT INTO tabela_macros_aa "
    "  (cliente_id, resposta_id, status, telefone_id, email_id) "
    "VALUES "
)
SQL_BULK_MACRO_SUFFIX = (
    " ON DUPLICATE KEY UPDATE "
    "  resposta_id = IF(status IN ('pendente','processando'), VALUES(resposta_id), resposta_id), "
    "  status      = IF(status IN ('pendente','processando'), VALUES(status),      status), "
    "  data_update = NOW()"
)


# ---------------------------------------------------------------------------
# Auxiliares
# ---------------------------------------------------------------------------

def conectar() -> pymysql.Connection:
    conn = pymysql.connect(**db_aguas_andinas(autocommit=False))
    with conn.cursor() as cur:
        cur.execute("SET SESSION innodb_lock_wait_timeout = 120")
    return conn


def carregar_clientes(conn: pymysql.Connection) -> dict[str, int]:
    """Carrega {rut: cliente_id} de todos os clientes (SSCursor streaming)."""
    print("Carregando clientes em memória...", flush=True)
    ruts: dict[str, int] = {}
    with conn.cursor(pymysql.cursors.SSCursor) as cur:
        cur.execute("SELECT rut, id FROM clientes")
        loaded = 0
        while True:
            chunk = cur.fetchmany(50_000)
            if not chunk:
                break
            for rut_db, cid in chunk:
                ruts[str(rut_db)] = cid   # mantém apenas o primeiro cliente_id por RUT
            loaded += len(chunk)
            if loaded % 500_000 == 0:
                print(f"  ...{loaded:,} carregados", flush=True)
    print(f"  Total: {len(ruts):,} clientes", flush=True)
    return ruts


def listar_csvs(caminho: Path | None) -> list[Path]:
    if caminho:
        if not caminho.exists():
            print(f"[ERRO] Arquivo não encontrado: {caminho}")
            sys.exit(1)
        return [caminho]

    csvs = sorted(RESULTADO_DIR.glob("*_RESULTADO.csv"))
    if not csvs:
        print(f"[AVISO] Nenhum arquivo *_RESULTADO.csv em {RESULTADO_DIR}")
        sys.exit(0)
    return csvs


def contar_linhas(caminho: Path) -> int:
    with open(caminho, encoding="utf-8") as f:
        return sum(1 for _ in f) - 1  # desconta cabeçalho


def _bulk_exec(cur, base_sql: str, rows: list[tuple], suffix: str = "") -> int:
    """INSERT em lote com múltiplos VALUES. Retorna rowcount."""
    if not rows:
        return 0
    ph = ",".join(["(%s)" % ",".join(["%s"] * len(rows[0]))] * len(rows))
    flat = [v for row in rows for v in row]
    cur.execute(base_sql + ph + suffix, flat)
    return cur.rowcount


def processar_csv(
    conn: pymysql.Connection,
    caminho: Path,
    clientes: dict[str, int],
    dry_run: bool,
) -> None:
    total = contar_linhas(caminho)
    print(f"\n{SEP}")
    print(f"Arquivo : {caminho.name}")
    print(f"Total   : {total} linhas")
    print(SEP)

    ok = skip = 0
    tel_count = email_count = macro_count = 0

    tel_batch:   list[tuple] = []   # (cliente_id, numero, 'validado')
    email_batch: list[tuple] = []   # (cliente_id, endereco, 'validado')
    macro_batch: list[tuple] = []   # (cliente_id, resposta_id, status, NULL, NULL, NOW, NOW)

    def flush(cur) -> None:
        nonlocal tel_count, email_count, macro_count
        if tel_batch:
            tel_count   += _bulk_exec(cur, SQL_BULK_TEL,   tel_batch)
            tel_batch.clear()
        if email_batch:
            email_count += _bulk_exec(cur, SQL_BULK_EMAIL, email_batch)
            email_batch.clear()
        if macro_batch:
            macro_count += _bulk_exec(cur, SQL_BULK_MACRO, macro_batch, SQL_BULK_MACRO_SUFFIX)
            macro_batch.clear()
        conn.commit()

    with open(caminho, encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f, delimiter=";")
        reader.fieldnames = [c.strip() for c in (reader.fieldnames or [])]

        with conn.cursor() as cur:
            for i, row in enumerate(reader, start=1):
                rut      = str(row.get("RUT",               "") or "").strip()
                sucesso  = str(row.get("SUCESSO",           "") or "").strip()
                telefone = str(row.get("TELEFONE_VALIDADO",  "") or "").strip()
                email    = str(row.get("EMAIL_VALIDADO",    "") or "").strip()
                erro     = str(row.get("ERRO",              "") or "").strip()

                if not rut:
                    skip += 1
                    continue

                cliente_id = clientes.get(rut)
                if cliente_id is None:
                    skip += 1
                    continue

                resposta_id, novo_status = interpretar(sucesso, telefone, email, erro)

                # normaliza telefone conforme regra: 8 dígitos -> prepend '9'; 9 dígitos -> keep; outros -> None
                def _normalize_phone(s: str):
                    import re
                    ds = re.sub(r"\D", "", str(s or ""))
                    if len(ds) == 8:
                        return '9' + ds
                    if len(ds) == 9:
                        return ds
                    return None

                normalized_tel = _normalize_phone(telefone) if telefone else None

                ok += 1

                if dry_run:
                    if i % 5000 == 0 or i == total:
                        print(f"  [{i}/{total}] dry-run ok={ok} skip={skip}")
                    continue

                if normalized_tel:
                    tel_batch.append((cliente_id, normalized_tel, "validado"))
                if email:
                    email_batch.append((cliente_id, email, "validado"))
                # telefone_id / email_id = NULL nesta passagem
                macro_batch.append((cliente_id, resposta_id, novo_status, None, None))

                if len(macro_batch) >= BATCH_SIZE:
                    flush(cur)

                if i % 50_000 == 0 or i == total:
                    print(
                        f"  [{i:>7}/{total}] ok={ok:>7} skip={skip} "
                        f"tel={tel_count:>6} email={email_count:>6} macro={macro_count:>7}",
                        flush=True,
                    )

            flush(cur)  # lote residual

    print(
        f"\n  Concluído — ok={ok} skip={skip} | "
        f"tel={tel_count} email={email_count} macro={macro_count}"
    )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Processa retorno da macro Águas Andinas")
    parser.add_argument("--dry-run",  action="store_true", help="Simula sem gravar no banco")
    parser.add_argument("--arquivo",  type=Path, default=None, help="CSV específico para processar")
    args = parser.parse_args()

    csvs = listar_csvs(args.arquivo)

    conn = conectar()
    try:
        clientes = carregar_clientes(conn)
        for csv_path in csvs:
            processar_csv(conn, csv_path, clientes, args.dry_run)
    finally:
        conn.close()

    print(f"\n{SEP}")
    print("Processamento finalizado.")


if __name__ == "__main__":
    main()
