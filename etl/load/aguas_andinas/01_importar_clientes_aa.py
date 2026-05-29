"""
01_importar_clientes_aa.py
==========================
Importa clientes da base estática para o banco bd_Automacoes_time_dados_aguas_andinas.

Arquivo de entrada:
    dados/bases/ENTREGA BASE NOMBRE DIRECCION FECH NAC.txt
    Colunas: rut ; dv ; nombre ; sexo ; direccion ; comuna ; region ; FECHA NAC
    Encoding: latin-1  |  Delimitador: ;

Tabelas preenchidas:
    staging_imports    → registra a execução com filename = NOME_LOTE
    clientes           → rut, dv, nome, sexo, data_nascimento
    enderecos          → direccion, comuna, region

Comportamento:
    • Idempotente: usa INSERT IGNORE em clientes (chave única = rut)
    • enderecos: insere só se o cliente ainda não tiver endereço
    • Processa em lotes de BATCH_SIZE linhas para não estourar memória
    • Exibe progresso a cada LOG_INTERVAL lotes

Uso:
    python etl/load/aguas_andinas/01_importar_clientes_aa.py
    python etl/load/aguas_andinas/01_importar_clientes_aa.py --dry-run
    python etl/load/aguas_andinas/01_importar_clientes_aa.py --limite 10000
"""

import argparse
import csv
import sys
from datetime import datetime, date
from pathlib import Path

import pymysql

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from config import db_aguas_andinas  # noqa: E402

# ---------------------------------------------------------------------------
# Configuração
# ---------------------------------------------------------------------------
BASE_FILE    = ROOT / "dados" / "bases" / "ENTREGA BASE NOMBRE DIRECCION FECH NAC.txt"
NOME_LOTE    = BASE_FILE.name   # nome exibido em staging_imports (= nome do arquivo)
ENCODING     = "latin-1"
DELIMITER    = ";"
BATCH_SIZE  = 2_000
LOG_INTERVAL = 50   # loga a cada N lotes (= a cada 100k linhas com batch 2k)

SEP = "=" * 70


# ---------------------------------------------------------------------------
# Normalização
# ---------------------------------------------------------------------------

def normalizar_rut(val: str) -> str | None:
    """Remove zeros à esquerda e retorna apenas dígitos do RUT."""
    v = str(val or "").strip()
    if not v:
        return None
    # Remove pontos e traços se houver
    v = v.replace(".", "").replace("-", "").split()[0]
    if not v.isdigit():
        return None
    return v.lstrip("0") or "0"


def normalizar_dv(val: str) -> str | None:
    v = str(val or "").strip().upper()
    return v if v in {str(i) for i in range(10)} | {"K"} else None


def normalizar_sexo(val: str) -> str | None:
    v = str(val or "").strip().upper()
    if v in ("MUJER", "F"):
        return "F"
    if v in ("VARON", "VARÓN", "M"):
        return "M"
    return None


def normalizar_data(val: str) -> date | None:
    """Aceita YYYYMMDD ou YYYY-MM-DD."""
    v = str(val or "").strip()
    if not v:
        return None
    try:
        if len(v) == 8 and v.isdigit():
            return datetime.strptime(v, "%Y%m%d").date()
        return datetime.strptime(v[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


def normalizar_str(val: str, max_len: int = 255) -> str | None:
    v = str(val or "").strip()
    return v[:max_len] if v else None


# ---------------------------------------------------------------------------
# Banco
# ---------------------------------------------------------------------------

def conectar(cfg: dict):
    return pymysql.connect(**cfg)


def buscar_ids_existentes(cursor, ruts: list[str]) -> dict[str, int]:
    """Retorna {rut: cliente_id} para os RUTs que já existem no banco."""
    if not ruts:
        return {}
    placeholders = ",".join(["%s"] * len(ruts))
    cursor.execute(
        f"SELECT rut, id FROM clientes WHERE rut IN ({placeholders})",
        ruts,
    )
    return {row[0]: row[1] for row in cursor.fetchall()}


def inserir_lote(cursor, clientes: list[dict], enderecos: list[dict], dry_run: bool, staging_id: int | None = None) -> tuple[int, int]:
    """
    Insere um lote de clientes e endereços.
    Retorna (inseridos_clientes, inseridos_enderecos).
    """
    if dry_run or not clientes:
        return 0, 0

    # ── Clientes ──────────────────────────────────────────────────────────
    sql_cliente = """
        INSERT IGNORE INTO clientes (rut, dv, nome, sexo, data_nascimento, staging_id)
        VALUES (%s, %s, %s, %s, %s, %s)
    """
    vals_cliente = [
        (c["rut"], c["dv"], c["nome"], c["sexo"], c["data_nascimento"], staging_id)
        for c in clientes
    ]
    cursor.executemany(sql_cliente, vals_cliente)
    # pymysql retorna -1 em executemany com INSERT IGNORE; conta manualmente
    inseridos_clientes = cursor.rowcount if cursor.rowcount >= 0 else len(vals_cliente)

    # ── IDs pós-insert (inclui já existentes) ─────────────────────────────
    ruts = [c["rut"] for c in clientes]
    id_map = buscar_ids_existentes(cursor, ruts)

    # ── Endereços (só se cliente não tiver ainda) ──────────────────────────
    # Busca clientes que já possuem endereço
    placeholders = ",".join(["%s"] * len(id_map))
    cursor.execute(
        f"SELECT cliente_id FROM enderecos WHERE cliente_id IN ({placeholders})",
        list(id_map.values()),
    )
    com_endereco = {row[0] for row in cursor.fetchall()}

    sql_endereco = """
        INSERT IGNORE INTO enderecos (cliente_id, direccion, comuna, region)
        VALUES (%s, %s, %s, %s)
    """
    vals_endereco = []
    for e in enderecos:
        cid = id_map.get(e["rut"])
        if cid and cid not in com_endereco:
            vals_endereco.append((cid, e["direccion"], e["comuna"], e["region"]))

    if vals_endereco:
        cursor.executemany(sql_endereco, vals_endereco)
    inseridos_enderecos = len(vals_endereco)

    return inseridos_clientes, inseridos_enderecos


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Importa clientes Águas Andinas para o banco")
    parser.add_argument("--dry-run", action="store_true", help="Simula sem gravar")
    parser.add_argument("--limite", type=int, default=0, help="Limita número de linhas (teste)")
    args = parser.parse_args()

    print(SEP)
    print("IMPORTAR CLIENTES  –  Águas Andinas")
    if args.dry_run:
        print("  [DRY-RUN] nenhuma alteração será gravada")
    print(SEP)
    print(f"  Arquivo : {BASE_FILE}")
    print(f"  Encoding: {ENCODING}")
    print(f"  Batch   : {BATCH_SIZE:,} linhas\n")

    cfg = db_aguas_andinas(autocommit=False)
    conn = conectar(cfg)

    total      = 0
    ignorados  = 0
    cli_ins    = 0
    end_ins    = 0
    erros      = 0

    batch_cli  = []
    batch_end  = []

    inicio = datetime.now()

    # ── Staging: abre registro da importação ──────────────────────────────
    staging_id = None
    if not args.dry_run:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO staging_imports (filename, status, started_at)
                VALUES (%s, 'processing', NOW())
                """,
                (NOME_LOTE,),
            )
            staging_id = cur.lastrowid
        conn.commit()
        print(f"  Staging ID : {staging_id} (\"{ NOME_LOTE}\")\n")

    try:
        with open(BASE_FILE, encoding=ENCODING, newline="") as f:
            reader = csv.DictReader(f, delimiter=DELIMITER)

            for i, row in enumerate(reader):
                if args.limite and i >= args.limite:
                    break

                total += 1

                rut = normalizar_rut(row.get("rut", ""))
                dv  = normalizar_dv(row.get("dv", ""))

                if not rut:
                    ignorados += 1
                    continue

                batch_cli.append({
                    "rut":             rut,
                    "dv":              dv,
                    "nome":            normalizar_str(row.get("nombre", ""), 255),
                    "sexo":            normalizar_sexo(row.get("sexo", "")),
                    "data_nascimento": normalizar_data(row.get("FECHA NAC", "")),
                })
                batch_end.append({
                    "rut":       rut,
                    "direccion": normalizar_str(row.get("direccion", ""), 255),
                    "comuna":    normalizar_str(row.get("comuna", ""), 100),
                    "region":    normalizar_str(row.get("region", ""), 100),
                })

                # Processa lote
                if len(batch_cli) >= BATCH_SIZE:
                    try:
                        with conn.cursor() as cur:
                            c, e = inserir_lote(cur, batch_cli, batch_end, args.dry_run, staging_id)
                        conn.commit()
                        cli_ins += c
                        end_ins += e
                    except Exception as ex:
                        conn.rollback()
                        erros += len(batch_cli)
                        print(f"  [ERRO lote ~linha {i}] {ex}")

                    batch_cli.clear()
                    batch_end.clear()

                    lote_num = total // BATCH_SIZE
                    if lote_num % LOG_INTERVAL == 0:
                        elapsed = (datetime.now() - inicio).total_seconds()
                        print(
                            f"  Linha {total:>9,} | "
                            f"clientes inseridos: {cli_ins:>8,} | "
                            f"enderecos: {end_ins:>8,} | "
                            f"{elapsed:.0f}s"
                        )

            # Lote residual
            if batch_cli:
                try:
                    with conn.cursor() as cur:
                        c, e = inserir_lote(cur, batch_cli, batch_end, args.dry_run, staging_id)
                    conn.commit()
                    cli_ins += c
                    end_ins += e
                except Exception as ex:
                    conn.rollback()
                    erros += len(batch_cli)
                    print(f"  [ERRO lote final] {ex}")

    finally:
        # ── Staging: fecha registro com totais ───────────────────────────
        if not args.dry_run and staging_id:
            status_final = 'completed' if erros == 0 else 'failed'
            try:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        UPDATE staging_imports
                        SET total_rows   = %s,
                            rows_success = %s,
                            rows_failed  = %s,
                            status       = %s,
                            finished_at  = NOW()
                        WHERE id = %s
                        """,
                        (total, total - ignorados - erros, erros, status_final, staging_id),
                    )
                conn.commit()
            except Exception as ex:
                print(f"  [AVISO] Não foi possível atualizar staging: {ex}")
        conn.close()

    elapsed = (datetime.now() - inicio).total_seconds()
    print(f"\n{SEP}")
    print(f"  Concluído em {elapsed:.1f}s")
    print(f"  Linhas lidas       : {total:>9,}")
    print(f"  Ignoradas (RUT inv): {ignorados:>9,}")
    print(f"  Clientes inseridos : {cli_ins:>9,}")
    print(f"  Endereços inseridos: {end_ins:>9,}")
    print(f"  Erros de lote      : {erros:>9,}")
    print(SEP)


if __name__ == "__main__":
    main()
