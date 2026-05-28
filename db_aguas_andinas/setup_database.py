"""
setup_database.py  –  Águas Andinas
====================================
Aplica o schema db_aguas_andinas/schema.sql no banco bd_aguas_andinas.

Uso:
    python db_aguas_andinas/setup_database.py
    python db_aguas_andinas/setup_database.py --dry-run   # só valida, não executa
"""

import argparse
import sys
from pathlib import Path

import pymysql

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from config import db_aguas_andinas  # noqa: E402

SCHEMA = Path(__file__).with_name("schema.sql")
SEP = "=" * 70


def split_statements(sql: str) -> list[str]:
    """
    Divide o SQL em statements individuais respeitando DELIMITER //.
    Necessário para triggers e stored procedures.
    """
    statements = []
    delimiter = ";"
    current = []

    for line in sql.splitlines():
        stripped = line.strip()

        # Troca de delimiter
        if stripped.upper().startswith("DELIMITER"):
            parts = stripped.split()
            if len(parts) >= 2:
                delimiter = parts[1]
            continue

        current.append(line)

        # Verifica se a linha termina com o delimiter atual
        if stripped.endswith(delimiter):
            stmt = "\n".join(current).strip()
            # Remove o delimiter do final
            if stmt.endswith(delimiter):
                stmt = stmt[: -len(delimiter)].strip()
            if stmt:
                statements.append(stmt)
            current = []

    # Captura qualquer restante
    stmt = "\n".join(current).strip()
    if stmt:
        statements.append(stmt)

    return statements


def main():
    parser = argparse.ArgumentParser(description="Aplica schema Águas Andinas no banco")
    parser.add_argument("--dry-run", action="store_true",
                        help="Exibe os statements sem executar")
    args = parser.parse_args()

    print(SEP)
    print("SETUP DATABASE  –  bd_Automacoes_time_dados_aguas_andinas")
    if args.dry_run:
        print("  [DRY-RUN] nenhuma alteração será gravada")
    print(SEP)

    sql_raw = SCHEMA.read_text(encoding="utf-8")
    statements = [s for s in split_statements(sql_raw) if s.strip()]

    print(f"  Schema  : {SCHEMA}")
    print(f"  Statements encontrados: {len(statements)}")

    if args.dry_run:
        for i, stmt in enumerate(statements, 1):
            print(f"\n--- Statement {i} ---")
            print(stmt[:200], "..." if len(stmt) > 200 else "")
        return

    cfg = db_aguas_andinas()
    # Conecta sem selecionar banco (para poder criar se necessário)
    cfg_no_db = {k: v for k, v in cfg.items() if k != "database"}

    print(f"\n  Host : {cfg['host']}:{cfg['port']}")
    print(f"  Banco: {cfg['database']}\n")

    conn = pymysql.connect(**cfg_no_db)
    try:
        with conn.cursor() as cur:
            # Garante que o banco existe
            cur.execute(
                f"CREATE DATABASE IF NOT EXISTS `{cfg['database']}` "
                f"CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"
            )
            cur.execute(f"USE `{cfg['database']}`;")

        conn.commit()

        ok = 0
        erros = []
        for i, stmt in enumerate(statements, 1):
            # Ignora USE statements (já selecionamos o banco acima)
            if stmt.strip().upper().startswith("USE "):
                continue
            try:
                with conn.cursor() as cur:
                    cur.execute(stmt)
                conn.commit()
                ok += 1
                print(f"  [{i:>3}] OK  — {stmt[:60].replace(chr(10), ' ')}")
            except pymysql.err.OperationalError as exc:
                erros.append((i, exc, stmt))
                print(f"  [{i:>3}] ERR — {exc}")

        print(f"\n{SEP}")
        print(f"  Concluído: {ok} OK  |  {len(erros)} erro(s)")
        if erros:
            print("\nStatements com erro:")
            for idx, exc, stmt in erros:
                print(f"  [{idx}] {exc}\n  SQL: {stmt[:120]}\n")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
