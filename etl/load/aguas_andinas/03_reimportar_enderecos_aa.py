"""
03_reimportar_enderecos_aa.py
==============================
Lê o arquivo de origem, aplica limpeza nos campos region/comuna/direccion,
grava uma cópia limpa do arquivo e faz UPDATE em massa na tabela `enderecos`.

Operações de limpeza:
  • region  → expande abreviações truncadas (ex: 'METROPOLIT' → 'METROPOLITANA DE SANTIAGO')
             → nulifica valores inválidos (comunas no campo errado, 'CHILE', etc.)
  • comuna  → nulifica valores que contêm dígitos, começam com caractere especial
             ou têm menos de 3 caracteres (endereços, coords, lixo)
  • direccion → mantém como está (apenas strip)

Arquivo limpo gerado:
    dados/bases/ENTREGA BASE NOMBRE DIRECCION FECH NAC_LIMPO.txt

Uso:
    python etl/load/aguas_andinas/03_reimportar_enderecos_aa.py
    python etl/load/aguas_andinas/03_reimportar_enderecos_aa.py --dry-run
    python etl/load/aguas_andinas/03_reimportar_enderecos_aa.py --limite 50000
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
from etl.load.aguas_andinas.limpeza_enderecos import (  # noqa: E402
    limpar_region, limpar_comuna, normalizar_rut
)

# ---------------------------------------------------------------------------
# Configuração
# ---------------------------------------------------------------------------
BASE_FILE    = ROOT / "dados" / "bases" / "ENTREGA BASE NOMBRE DIRECCION FECH NAC.txt"
LIMPO_FILE   = ROOT / "dados" / "bases" / "ENTREGA BASE NOMBRE DIRECCION FECH NAC_LIMPO.txt"
ENCODING     = "latin-1"
DELIMITER    = ";"
BATCH_SIZE   = 2_000
LOG_INTERVAL = 50

SEP = "=" * 70


def limpar_direccion(val: str) -> str | None:
    v = (val or "").strip()
    return v[:255] if v else None


# ---------------------------------------------------------------------------
# Etapa 1 — Gerar arquivo limpo
# ---------------------------------------------------------------------------
def gerar_arquivo_limpo(limite: int) -> dict:
    """Lê o arquivo original, limpa e grava LIMPO_FILE. Retorna estatísticas."""
    stats = {
        "total": 0, "sem_rut": 0,
        "region_expandida": 0, "region_nulificada": 0,
        "comuna_nulificada": 0,
    }

    with (
        open(BASE_FILE, encoding=ENCODING, newline="") as fin,
        open(LIMPO_FILE, "w", encoding="utf-8", newline="") as fout,
    ):
        reader  = csv.DictReader(fin, delimiter=DELIMITER)
        writer  = csv.DictWriter(fout, fieldnames=reader.fieldnames, delimiter=DELIMITER)
        writer.writeheader()

        for i, row in enumerate(reader):
            if limite and i >= limite:
                break

            stats["total"] += 1
            rut = normalizar_rut(row.get("rut", ""))
            if not rut:
                stats["sem_rut"] += 1
                writer.writerow(row)   # mantém linha original mesmo sem RUT
                continue

            # Limpeza region
            region_orig = (row.get("region") or "").strip()
            region_limpa = limpar_region(region_orig)
            if region_orig and not region_limpa:
                stats["region_nulificada"] += 1
            elif region_orig and region_limpa != region_orig:
                stats["region_expandida"] += 1

            # Limpeza comuna
            comuna_orig = (row.get("comuna") or "").strip()
            comuna_limpa = limpar_comuna(comuna_orig)
            if comuna_orig and not comuna_limpa:
                stats["comuna_nulificada"] += 1

            row["region"] = region_limpa or ""
            row["comuna"] = comuna_limpa or ""
            row["direccion"] = limpar_direccion(row.get("direccion", "")) or ""
            writer.writerow(row)

    return stats


# ---------------------------------------------------------------------------
# Etapa 2 — UPDATE no banco a partir do arquivo limpo
# ---------------------------------------------------------------------------
def atualizar_banco(dry_run: bool, limite: int) -> dict:
    """Lê LIMPO_FILE e faz UPDATE em massa na tabela enderecos."""
    stats = {"total": 0, "sem_rut": 0, "atualizados": 0, "erros": 0}

    cfg  = db_aguas_andinas(autocommit=False)
    conn = pymysql.connect(**cfg)

    SQL_UPDATE = """
        UPDATE enderecos e
        INNER JOIN clientes c ON c.id = e.cliente_id
        SET e.direccion = %s,
            e.comuna    = %s,
            e.region    = %s
        WHERE c.rut = %s
    """

    batch: list[tuple] = []
    inicio = datetime.now()

    try:
        with open(LIMPO_FILE, encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f, delimiter=DELIMITER)

            for i, row in enumerate(reader):
                if limite and i >= limite:
                    break

                stats["total"] += 1
                rut = normalizar_rut(row.get("rut", ""))
                if not rut:
                    stats["sem_rut"] += 1
                    continue

                direccion = row.get("direccion") or None
                comuna    = row.get("comuna")    or None
                region    = row.get("region")    or None

                batch.append((direccion, comuna, region, rut))

                if len(batch) >= BATCH_SIZE:
                    if not dry_run:
                        try:
                            with conn.cursor() as cur:
                                cur.executemany(SQL_UPDATE, batch)
                            conn.commit()
                            stats["atualizados"] += len(batch)
                        except Exception as ex:
                            conn.rollback()
                            stats["erros"] += len(batch)
                            print(f"  [ERRO lote ~linha {i}] {ex}")
                    else:
                        stats["atualizados"] += len(batch)   # dry-run: conta apenas

                    batch.clear()

                    lote_num = stats["total"] // BATCH_SIZE
                    if lote_num % LOG_INTERVAL == 0:
                        elapsed = (datetime.now() - inicio).total_seconds()
                        print(
                            f"  Linha {stats['total']:>9,} | "
                            f"atualizados: {stats['atualizados']:>8,} | "
                            f"{elapsed:.0f}s"
                        )

        # Lote residual
        if batch:
            if not dry_run:
                try:
                    with conn.cursor() as cur:
                        cur.executemany(SQL_UPDATE, batch)
                    conn.commit()
                    stats["atualizados"] += len(batch)
                except Exception as ex:
                    conn.rollback()
                    stats["erros"] += len(batch)
                    print(f"  [ERRO lote residual] {ex}")
            else:
                stats["atualizados"] += len(batch)

    finally:
        conn.close()

    return stats


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true",
                        help="Gera arquivo limpo mas não altera o banco")
    parser.add_argument("--limite", type=int, default=0,
                        help="Processa apenas N linhas (teste)")
    args = parser.parse_args()

    tag = " [DRY-RUN]" if args.dry_run else ""
    print(SEP)
    print(f"REIMPORTAR ENDEREÇOS{tag}  —  {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}")
    print(SEP)
    print(f"  Origem : {BASE_FILE.name}")
    print(f"  Saída  : {LIMPO_FILE.name}")

    # ------------------------------------------------------------------
    # Etapa 1: Gerar arquivo limpo
    # ------------------------------------------------------------------
    print(f"\n{SEP}")
    print("ETAPA 1 — Limpeza e geração do arquivo limpo")
    print(SEP)
    t0 = datetime.now()
    s1 = gerar_arquivo_limpo(args.limite)
    elapsed = (datetime.now() - t0).total_seconds()

    print(f"  Linhas processadas   : {s1['total']:>10,}")
    print(f"  Sem RUT (ignoradas)  : {s1['sem_rut']:>10,}")
    print(f"  Regiões expandidas   : {s1['region_expandida']:>10,}")
    print(f"  Regiões nulificadas  : {s1['region_nulificada']:>10,}")
    print(f"  Comunas nulificadas  : {s1['comuna_nulificada']:>10,}")
    print(f"  Arquivo limpo gravado: {LIMPO_FILE}")
    print(f"  Tempo: {elapsed:.1f}s")

    # ------------------------------------------------------------------
    # Etapa 2: UPDATE no banco
    # ------------------------------------------------------------------
    print(f"\n{SEP}")
    print(f"ETAPA 2 — UPDATE na tabela enderecos{tag}")
    print(SEP)
    t0 = datetime.now()
    s2 = atualizar_banco(args.dry_run, args.limite)
    elapsed = (datetime.now() - t0).total_seconds()

    print(f"\n  Linhas processadas   : {s2['total']:>10,}")
    print(f"  Sem RUT (ignoradas)  : {s2['sem_rut']:>10,}")
    print(f"  Endereços atualizados: {s2['atualizados']:>10,}")
    print(f"  Erros                : {s2['erros']:>10,}")
    print(f"  Tempo: {elapsed:.1f}s")

    print(f"\n{'Simulação concluída — banco não foi alterado.' if args.dry_run else 'Reimportação concluída.'}")
    print(f"Fim: {datetime.now().strftime('%H:%M:%S')}")


if __name__ == "__main__":
    main()
