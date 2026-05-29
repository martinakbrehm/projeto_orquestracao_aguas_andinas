"""
04_atualizar_enderecos_limpo5.py  (v2 — temp table, checkpoint, ~50x mais rápido)
===================================================================================
Estratégia de performance:
  • ANTES  : executemany(UPDATE) → 2.000 round trips por lote → ~136ms/linha
  • AGORA  : INSERT multi-row em temp table + UPDATE JOIN → 3 round trips por lote

Fluxo por lote:
  1. INSERT INTO tmp_update VALUES (...), (...), ...  ← 1 round trip
  2. UPDATE enderecos INNER JOIN clientes INNER JOIN tmp_update  ← 1 round trip
  3. DELETE FROM tmp_update  ← 1 round trip

Checkpoint:
  • Salva a última linha confirmada em .checkpoint_limpo5.txt
  • Ao reiniciar, pula linhas já processadas automaticamente

Limpezas no arquivo:
  LIMPO  → expansão de regiões truncadas + nulificação básica
  LIMPO2 → remoção de nomes de região no campo comuna + typos conhecidos
  LIMPO3 → correção de truncamentos de cidades por prefixo
  LIMPO4 → normalização de espaços duplos e pontuação
  LIMPO5 → trailing dots, letra extra no fim, palavras coladas, S faltando

Uso:
    python etl/load/aguas_andinas/04_atualizar_enderecos_limpo5.py
    python etl/load/aguas_andinas/04_atualizar_enderecos_limpo5.py --dry-run
    python etl/load/aguas_andinas/04_atualizar_enderecos_limpo5.py --reset   # ignora checkpoint
"""

import argparse
import csv
import sys
from datetime import datetime
from pathlib import Path

import pymysql

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from config import db_aguas_andinas  # noqa: E402

LIMPO5_FILE     = ROOT / "dados" / "bases" / "ENTREGA BASE NOMBRE DIRECCION FECH NAC_LIMPO5.txt"
CHECKPOINT_FILE = Path(__file__).parent / ".checkpoint_limpo5.txt"
DELIMITER       = ";"
BATCH_SIZE      = 10_000
LOG_INTERVAL    = 10
TOTAL_LINHAS    = 6_283_947

SEP = "=" * 70


def normalizar_rut(val: str) -> str | None:
    v = str(val or "").strip().replace(".", "").replace("-", "").split()[0] if val else ""
    if not v or not v.isdigit():
        return None
    return v.lstrip("0") or "0"


def ler_checkpoint() -> int:
    try:
        return int(CHECKPOINT_FILE.read_text().strip())
    except Exception:
        return 0


def salvar_checkpoint(linha: int) -> None:
    CHECKPOINT_FILE.write_text(str(linha))


def criar_temp_table(conn) -> None:
    with conn.cursor() as cur:
        cur.execute("""
            CREATE TEMPORARY TABLE IF NOT EXISTS tmp_update (
                rut       CHAR(9)       NOT NULL,
                direccion VARCHAR(512)  DEFAULT NULL,
                comuna    VARCHAR(255)  DEFAULT NULL,
                region    VARCHAR(255)  DEFAULT NULL,
                PRIMARY KEY (rut)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """)
    conn.commit()


def inserir_lote(conn, batch: list[tuple]) -> None:
    """INSERT multi-row na temp table — 1 round trip para N linhas."""
    placeholders = ", ".join(["(%s,%s,%s,%s)"] * len(batch))
    sql = f"INSERT INTO tmp_update (rut, direccion, comuna, region) VALUES {placeholders}"
    params = [v for row in batch for v in row]
    with conn.cursor() as cur:
        cur.execute(sql, params)


def atualizar_do_temp(conn) -> int:
    """UPDATE enderecos via JOIN com tmp_update — 1 round trip."""
    sql = """
        UPDATE enderecos e
        INNER JOIN clientes c ON c.id = e.cliente_id
        INNER JOIN tmp_update t ON t.rut = c.rut
        SET e.direccion = t.direccion,
            e.comuna    = t.comuna,
            e.region    = t.region
    """
    with conn.cursor() as cur:
        cur.execute(sql)
        return cur.rowcount


def atualizar_banco(dry_run: bool, inicio_linha: int) -> dict:
    stats = {"total": 0, "sem_rut": 0, "atualizados": 0, "erros": 0}

    cfg  = db_aguas_andinas(autocommit=False)
    conn = pymysql.connect(**cfg)
    if not dry_run:
        criar_temp_table(conn)

    batch: list[tuple] = []
    t_inicio = datetime.now()
    lote_num = 0

    try:
        with open(LIMPO5_FILE, encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f, delimiter=DELIMITER)

            for i, row in enumerate(reader):
                if i < inicio_linha:
                    continue

                stats["total"] += 1

                rut = normalizar_rut(row.get("rut", ""))
                if not rut:
                    stats["sem_rut"] += 1
                    continue

                batch.append((
                    rut,
                    row.get("direccion") or None,
                    row.get("comuna")    or None,
                    row.get("region")    or None,
                ))

                if len(batch) >= BATCH_SIZE:
                    lote_num += 1
                    if not dry_run:
                        try:
                            inserir_lote(conn, batch)
                            rows = atualizar_do_temp(conn)
                            with conn.cursor() as cur:
                                cur.execute("DELETE FROM tmp_update")
                            conn.commit()
                            stats["atualizados"] += rows
                            salvar_checkpoint(i)
                        except Exception as ex:
                            conn.rollback()
                            stats["erros"] += len(batch)
                            print(f"  [ERRO lote {lote_num} ~linha {i}] {ex}")
                    else:
                        stats["atualizados"] += len(batch)

                    batch.clear()

                    if lote_num % LOG_INTERVAL == 0:
                        elapsed = (datetime.now() - t_inicio).total_seconds()
                        pct = (i / TOTAL_LINHAS) * 100
                        vel = stats["total"] / elapsed if elapsed > 0 else 0
                        restante = (TOTAL_LINHAS - i) / vel if vel > 0 else 0
                        print(
                            f"  Linha {i:>9,} ({pct:5.1f}%) | "
                            f"atualizados: {stats['atualizados']:>9,} | "
                            f"{elapsed:,.0f}s | "
                            f"{vel:,.0f} lin/s | "
                            f"~{restante/60:.0f}min restantes"
                        )

        # Lote residual
        if batch:
            lote_num += 1
            if not dry_run:
                try:
                    inserir_lote(conn, batch)
                    rows = atualizar_do_temp(conn)
                    with conn.cursor() as cur:
                        cur.execute("DELETE FROM tmp_update")
                    conn.commit()
                    stats["atualizados"] += rows
                    salvar_checkpoint(TOTAL_LINHAS)
                except Exception as ex:
                    conn.rollback()
                    stats["erros"] += len(batch)
                    print(f"  [ERRO lote residual] {ex}")
            else:
                stats["atualizados"] += len(batch)

    finally:
        conn.close()

    return stats


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true",
                        help="Valida o arquivo mas não altera o banco")
    parser.add_argument("--reset", action="store_true",
                        help="Ignora checkpoint e começa do início")
    args = parser.parse_args()

    inicio_linha = 0
    if not args.reset and not args.dry_run:
        inicio_linha = ler_checkpoint()

    tag = " [DRY-RUN]" if args.dry_run else ""
    print(SEP)
    print(f"UPDATE ENDEREÇOS — LIMPO5 v2{tag}  —  {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}")
    print(SEP)
    print(f"  Arquivo    : {LIMPO5_FILE.name}")
    print(f"  Limpezas   : LIMPO->LIMPO2->LIMPO3->LIMPO4->LIMPO5 (5 etapas)")
    print(f"  Estratégia : temp table + INSERT multi-row + UPDATE JOIN")
    print(f"  Lote       : {BATCH_SIZE:,} linhas")
    if inicio_linha:
        print(f"  Checkpoint : retomando da linha {inicio_linha:,}")

    if not LIMPO5_FILE.exists():
        print(f"\n[ERRO] Arquivo não encontrado: {LIMPO5_FILE}")
        sys.exit(1)

    t0 = datetime.now()
    stats = atualizar_banco(args.dry_run, inicio_linha)
    elapsed = (datetime.now() - t0).total_seconds()

    print(SEP)
    print(f"  Linhas processadas   : {stats['total']:>10,}")
    print(f"  Sem RUT (ignoradas)  : {stats['sem_rut']:>10,}")
    print(f"  Endereços atualizados: {stats['atualizados']:>10,}")
    print(f"  Erros                : {stats['erros']:>10,}")
    vel = stats["total"] / elapsed if elapsed > 0 else 0
    print(f"  Tempo total          : {elapsed:>10,.0f}s ({elapsed/60:.1f}min)")
    print(f"  Velocidade           : {vel:>10,.0f} lin/s")

    if args.dry_run:
        print("\nSimulação concluída — banco NÃO foi alterado.")
    elif stats["erros"] == 0:
        print("\nAtualização concluída com sucesso.")
        if CHECKPOINT_FILE.exists():
            CHECKPOINT_FILE.unlink()
    else:
        print(f"\nAtualização com {stats['erros']:,} erros — checkpoint salvo para retomar.")

    print(f"Fim: {datetime.now().strftime('%H:%M:%S')}")


if __name__ == "__main__":
    main()
