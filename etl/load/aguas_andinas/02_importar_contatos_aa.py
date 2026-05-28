"""
02_importar_contatos_aa.py
==========================
Importa telefones e e-mails históricos para o banco bd_Automacoes_time_dados_aguas_andinas.
Complementa o script 01_importar_clientes_aa.py — usa o mesmo registro em staging_imports.

Arquivos de entrada:
    dados/bases/ENTREGA CELULAR.txt   → Rut ; Celular
    dados/bases/ENTREGA CORREOv.txt   → Rut ; Email
    Encoding: latin-1  |  Delimitador: ;

Tabelas preenchidas:
    telefones  → numero, origem=enriquecimento, staging_id
    emails     → endereco, origem=enriquecimento, staging_id

Staging:
    Reutiliza o registro existente em staging_imports (--staging-id, default: último registro).
    Ao concluir, atualiza total_rows e rows_success acumulando ao que já existia.

Comportamento:
    • Idempotente: UNIQUE KEY (cliente_id, numero, origem) — duplicatas ignoradas
    • RUTs sem match em clientes são descartados (ignorados)
    • Processa em lotes de BATCH_SIZE linhas

Uso:
    python etl/load/aguas_andinas/02_importar_contatos_aa.py
    python etl/load/aguas_andinas/02_importar_contatos_aa.py --staging-id 1
    python etl/load/aguas_andinas/02_importar_contatos_aa.py --dry-run
    python etl/load/aguas_andinas/02_importar_contatos_aa.py --limite 10000
"""
# Otimização: carrega todos os RUTs -> cliente_id em RAM
# ---------------------------------------------------------------------------
def carregar_ruts_cliente_ids(conn):
    """Retorna dict rut->cliente_id para todos os clientes."""
    print("Carregando todos os RUTs de clientes em memória...", flush=True)
    with conn.cursor() as cur:
        cur.execute("SELECT rut, id FROM clientes")
        return {str(r[0]): r[1] for r in cur.fetchall()}

import argparse
import csv
import sys
from datetime import datetime
from pathlib import Path

import pymysql
ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from config import db_aguas_andinas  # noqa: E402

# ---------------------------------------------------------------------------
# Configuração
# ---------------------------------------------------------------------------
CEL_FILE   = ROOT / "dados" / "bases" / "ENTREGA CELULAR.txt"
EMAIL_FILE = ROOT / "dados" / "bases" / "ENTREGA CORREOv.txt"
ENCODING   = "latin-1"
DELIMITER  = ";"
BATCH_SIZE = 500
MAX_RETRIES = 5
RETRY_SLEEP = 10  # segundos entre retries em lock error
LOG_INTERVAL = 10   # loga a cada N lotes (50 k linhas)

SEP = "=" * 70


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def normalizar_rut(val: str) -> str | None:
    v = str(val or "").strip().replace(".", "").replace("-", "").split()[0]
    if not v.isdigit():
        return None
    return v.lstrip("0") or "0"


WHITELIST_CHUNK = 5_000


def buscar_cliente_ids(cursor, ruts: list[str]) -> dict[str, list[int]]:
    """Retorna {rut: [cliente_id, ...]} para os RUTs presentes no banco."""
    if not ruts:
        return {}
    ph = ",".join(["%s"] * len(ruts))
    cursor.execute(f"SELECT rut, id FROM clientes WHERE rut IN ({ph})", ruts)
    result: dict[str, list[int]] = {}
    for rut, cid in cursor.fetchall():
        result.setdefault(rut, []).append(cid)
    return result


def carregar_ruts_dict(cursor, ruts: set[str]) -> dict[str, list[int]]:
    """Carrega {rut: [cliente_id, ...]} para todos os RUTs, em chunks de WHITELIST_CHUNK."""
    result: dict[str, list[int]] = {}
    ruts_list = list(ruts)
    total = len(ruts_list)
    print(f"  Carregando {total:,} RUTs em memória (chunks de {WHITELIST_CHUNK:,})...", flush=True)
    for i in range(0, total, WHITELIST_CHUNK):
        chunk = ruts_list[i:i + WHITELIST_CHUNK]
        ph = ",".join(["%s"] * len(chunk))
        cursor.execute(f"SELECT rut, id FROM clientes WHERE rut IN ({ph})", chunk)
        for rut, cid in cursor.fetchall():
            result.setdefault(rut, []).append(cid)
        if (i // WHITELIST_CHUNK) % 500 == 0 and i > 0:
            print(f"  ...{i:,}/{total:,} RUTs consultados", flush=True)
    print(f"  RUTs encontrados no banco: {len(result):,}", flush=True)
    return result


def _bulk_insert(cursor, table: str, cols: str, batch: list[tuple]) -> int:
    """Faz INSERT IGNORE com todos os valores em um único statement SQL."""
    if not batch:
        return 0
    ph = ",".join(["(%s,%s,%s)"] * len(batch))
    flat = [v for row in batch for v in row]
    sql = f"INSERT IGNORE INTO {table} ({cols}, origem, staging_id) VALUES {ph}"
    # Substitui os %s extras da string de origem
    sql = f"INSERT IGNORE INTO {table} ({cols}, origem, staging_id) VALUES " + ",".join(
        ["(%s,%s,'enriquecimento',%s)"] * len(batch)
    )
    flat = [v for row in batch for v in row]
    cursor.execute(sql, flat)
    return cursor.rowcount


def inserir_telefones(cursor, batch: list[tuple], dry_run: bool) -> int:
    """Insere lote de (cliente_id, numero, staging_id). Retorna estimativa inserida."""
    if dry_run or not batch:
        return 0
    return _bulk_insert(cursor, "telefones", "cliente_id, numero", batch)


def inserir_emails(cursor, batch: list[tuple], dry_run: bool) -> int:
    """Insere lote de (cliente_id, endereco, staging_id). Retorna estimativa inserida."""
    if dry_run or not batch:
        return 0
    return _bulk_insert(cursor, "emails", "cliente_id, endereco", batch)


def obter_staging_id(cursor, staging_id_arg: int | None) -> int | None:
    """Retorna o staging_id a usar: argumento explícito ou último registro."""
    if staging_id_arg:
        cursor.execute("SELECT id, filename FROM staging_imports WHERE id = %s", (staging_id_arg,))
    else:
        cursor.execute("SELECT id, filename FROM staging_imports ORDER BY id DESC LIMIT 1")
    row = cursor.fetchone()
    if row:
        print(f"  Staging  : id={row[0]} (\"{row[1]}\")")
        return row[0]
    return None


def atualizar_staging(cursor, staging_id: int, total: int, sucesso: int, erros: int):
    """Acumula total_rows e rows_success ao que já existia no registro."""
    cursor.execute(
        """
        UPDATE staging_imports
        SET total_rows   = total_rows   + %s,
            rows_success = rows_success + %s,
            rows_failed  = rows_failed  + %s,
            finished_at  = NOW()
        WHERE id = %s
        """,
        (total, sucesso, erros, staging_id),
    )


# ---------------------------------------------------------------------------
# Processamento de um arquivo
# ---------------------------------------------------------------------------

def processar_arquivo(
    conn,
    filepath: Path,
    col_valor: str,
    tipo: str,          # 'telefone' ou 'email'
    staging_id: int,
    dry_run: bool,
    limite: int,
) -> tuple[int, int, int]:
    """
    Lê o arquivo e insere os contatos.
    Para emails: pré-carrega todos os rut→[cliente_ids] em RAM (com chunks).
    Um RUT pode ter múltiplos cliente_ids — cada combinação gera uma entrada.
    Retorna (total_lido, inseridos, ignorados).
    """
    total = 0
    inseridos = 0
    ignorados = 0
    erros = 0
    batch: list[tuple] = []
    inicio = datetime.now()
    ruts_dict: dict[str, list[int]] = {}

    insert_fn = inserir_telefones if tipo == "telefone" else inserir_emails

    # Para emails: carrega TODOS os clientes do banco em memória (streaming SSCursor)
    if tipo == "email":
        print("Carregando todos os clientes do banco em memória...", flush=True)
        with conn.cursor(pymysql.cursors.SSCursor) as sscur:
            sscur.execute("SELECT rut, id FROM clientes")
            loaded = 0
            while True:
                chunk = sscur.fetchmany(50_000)
                if not chunk:
                    break
                for rut_db, cid in chunk:
                    ruts_dict.setdefault(str(rut_db), []).append(cid)
                loaded += len(chunk)
                if loaded % 500_000 == 0:
                    print(f"  ...{loaded:,} clientes carregados", flush=True)
        print(f"  Clientes carregados: {len(ruts_dict):,}", flush=True)

    def _flush_batch(batch: list[tuple], i: int) -> tuple[int, int]:
        """Tenta inserir o lote com retries. Retorna (inseridos, erros)."""
        ins_total = 0
        err_total = 0
        for tentativa in range(MAX_RETRIES):
            try:
                with conn.cursor() as cur:
                    ins = insert_fn(cur, batch, dry_run)
                conn.commit()
                ins_total += ins
                return ins_total, err_total
            except pymysql.err.OperationalError as ex:
                conn.rollback()
                if tentativa < MAX_RETRIES - 1:
                    import time
                    print(f"  [RETRY {tentativa+1}/{MAX_RETRIES} ~linha {i}] {ex} – aguardando {RETRY_SLEEP}s", flush=True)
                    time.sleep(RETRY_SLEEP)
                else:
                    err_total += len(batch)
                    print(f"  [ERRO definitivo ~linha {i}] {ex}")
            except Exception as ex:
                conn.rollback()
                err_total += len(batch)
                print(f"  [ERRO lote ~linha {i}] {ex}")
                break
        return ins_total, err_total

    with open(filepath, encoding=ENCODING, newline="") as f:
        reader = csv.DictReader(f, delimiter=DELIMITER)
        for i, row in enumerate(reader):
            if limite and i >= limite:
                break
            total += 1
            rut = normalizar_rut(row.get("Rut", ""))
            valor = str(row.get(col_valor, "")).strip()
            if not rut or not valor:
                ignorados += 1
                continue

            if tipo == "email":
                # Expande para todos os cliente_ids do RUT
                cids = ruts_dict.get(rut)
                if not cids:
                    ignorados += 1
                    continue
                for cid in cids:
                    batch.append((cid, valor, staging_id))
            else:
                # Telefones: armazena RUT, resolve em batch
                batch.append((rut, valor, staging_id))

            if len(batch) >= BATCH_SIZE:
                if tipo == "telefone":
                    # Resolve RUTs para cliente_ids
                    with conn.cursor() as cur:
                        id_map = buscar_cliente_ids(cur, list({b[0] for b in batch}))
                    resolved = [
                        (cid, b[1], b[2])
                        for b in batch if b[0] in id_map
                        for cid in id_map[b[0]]
                    ]
                    ignorados += len(batch) - len({b[0] for b in batch if b[0] in id_map})
                    ins, err = _flush_batch(resolved, i)
                else:
                    ins, err = _flush_batch(batch, i)
                inseridos += ins
                erros += err
                batch.clear()
                lote_num = total // BATCH_SIZE
                if lote_num % LOG_INTERVAL == 0:
                    elapsed = (datetime.now() - inicio).total_seconds()
                    print(
                        f"  [{tipo}] Linha {total:>10,} | "
                        f"inseridos: {inseridos:>9,} | "
                        f"ignorados: {ignorados:>8,} | "
                        f"{elapsed:.0f}s",
                        flush=True,
                    )
        # Lote residual
        if batch:
            if tipo == "telefone":
                with conn.cursor() as cur:
                    id_map = buscar_cliente_ids(cur, list({b[0] for b in batch}))
                resolved = [
                    (cid, b[1], b[2])
                    for b in batch if b[0] in id_map
                    for cid in id_map[b[0]]
                ]
                ignorados += len(batch) - len({b[0] for b in batch if b[0] in id_map})
                ins, err = _flush_batch(resolved, i)
            else:
                ins, err = _flush_batch(batch, i)
            inseridos += ins
            erros += err

    return total, inseridos, ignorados + erros



# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Importa telefones e e-mails históricos")
    parser.add_argument("--dry-run",       action="store_true", help="Simula sem gravar")
    parser.add_argument("--limite",        type=int, default=0, help="Limita linhas por arquivo (teste)")
    parser.add_argument("--staging-id",    type=int, default=None, help="ID do staging_imports a reutilizar")
    parser.add_argument("--apenas-emails", action="store_true", help="Processa apenas e-mails (pula telefones)")
    parser.add_argument("--apenas-tel",    action="store_true", help="Processa apenas telefones (pula e-mails)")
    args = parser.parse_args()

    print(SEP)
    print("IMPORTAR CONTATOS  –  Águas Andinas  (telefones + e-mails)")
    if args.dry_run:
        print("  [DRY-RUN] nenhuma alteração será gravada")
    print(SEP)

    cfg = db_aguas_andinas(autocommit=False, read_timeout=7200, write_timeout=7200)
    conn = pymysql.connect(**cfg)
    # Aumenta timeout de lock na sessão (padrão é 50s)
    with conn.cursor() as _cur:
        _cur.execute("SET SESSION innodb_lock_wait_timeout = 300")
    conn.commit()

    # Obtém staging_id
    staging_id = None
    if not args.dry_run:
        with conn.cursor() as cur:
            staging_id = obter_staging_id(cur, args.staging_id)
        if not staging_id:
            print("  [ERRO] Nenhum registro em staging_imports. Execute 01_importar_clientes_aa.py primeiro.")
            conn.close()
            sys.exit(1)

    print()

    total_geral   = 0
    sucesso_geral = 0
    ignor_geral   = 0

    arquivos = [
        (CEL_FILE,   "Celular", "telefone"),
        (EMAIL_FILE, "Email",   "email"),
    ]
    if args.apenas_emails:
        arquivos = [(EMAIL_FILE, "Email", "email")]
    elif args.apenas_tel:
        arquivos = [(CEL_FILE, "Celular", "telefone")]

    for filepath, col, tipo in arquivos:
        print(f"  Arquivo: {filepath.name}", flush=True)
        t, ins, ign = processar_arquivo(
            conn, filepath, col, tipo, staging_id, args.dry_run, args.limite
        )
        elapsed = 0
        print(f"  → {tipo}: {t:,} lidos | {ins:,} inseridos | {ign:,} ignorados\n")
        total_geral   += t
        sucesso_geral += ins
        ignor_geral   += ign

    # Atualiza staging
    if not args.dry_run and staging_id:
        try:
            with conn.cursor() as cur:
                atualizar_staging(cur, staging_id, total_geral, sucesso_geral, total_geral - sucesso_geral)
            conn.commit()
        except Exception as ex:
            print(f"  [AVISO] Não foi possível atualizar staging: {ex}")

    conn.close()

    print(SEP)
    print(f"  Total lido        : {total_geral:>10,}")
    print(f"  Inseridos         : {sucesso_geral:>10,}")
    print(f"  Ignorados/sem RUT : {ignor_geral:>10,}")
    print(SEP)


if __name__ == "__main__":
    main()
