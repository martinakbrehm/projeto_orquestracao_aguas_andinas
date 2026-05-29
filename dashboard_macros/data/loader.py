import sys
import time
from pathlib import Path

import pymysql
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from config import db_cpfl, db_aguas_andinas  # noqa: E402

DB_CONFIG = db_cpfl()
DB_CONFIG_AA = db_aguas_andinas()

_CACHE: dict = {}        # cache por tipo {'macro': df} — sem TTL, vive durante o processo
_CACHE_STATS: dict = {}  # cache para stats_por_arquivo / cobertura
_CACHE_STATS_TTL = 3600  # segundos (1 hora)

# ---------------------------------------------------------------------------
# Tabela materializada — populada pela stored procedure
# sp_refresh_dashboard_macros_agg() chamada ao final do ETL.
# SELECT simples em tabela indexada: latência <1ms.
# ---------------------------------------------------------------------------
# Query direta na tabela_macros_cpfl + respostas (sem tabela materializada)
SQLs = {
    "macro": """
        SELECT
            DATE(tm.data_update)  AS dia,
            tm.status             AS status,
            r.mensagem            AS mensagem,
            r.status              AS resposta_status,
            NULL                  AS empresa,
            NULL                  AS fornecedor,
            NULL                  AS arquivo_origem,
            COUNT(*)              AS qtd
        FROM tabela_macros_cpfl tm
        JOIN respostas r ON r.id = tm.resposta_id
        WHERE tm.status NOT IN ('pendente', 'processando')
        GROUP BY DATE(tm.data_update), tm.status, r.mensagem, r.status
        ORDER BY dia DESC
    """,
}

SQL_AA = """
    SELECT
        DATE(tm.data_update)  AS dia,
        tm.status             AS status,
        r.mensagem            AS mensagem,
        COUNT(*)              AS qtd
    FROM tabela_macros_aa tm
    LEFT JOIN respostas r ON r.id = tm.resposta_id
    WHERE tm.status NOT IN ('pendente', 'processando')
    GROUP BY DATE(tm.data_update), tm.status, r.mensagem
    ORDER BY dia DESC
"""

SQL_AA_STATUS_DIST = """
    SELECT
        tm.status  AS status,
        COUNT(*)   AS qtd
    FROM tabela_macros_aa tm
    GROUP BY tm.status
    ORDER BY qtd DESC
"""



def carregar_dados(tipo: str = "macro") -> pd.DataFrame:
    """Carrega dados do banco de dados.

    tipo: 'macro' | 'aguas_andinas'
    Resultado é cacheado em memória por tipo (sem TTL — vive durante o processo).
    """
    if tipo == "aguas_andinas":
        if tipo in _CACHE:
            return _CACHE[tipo].copy()
        try:
            conn = pymysql.connect(**DB_CONFIG_AA)
            with conn.cursor() as cur:
                cur.execute(SQL_AA)
                cols = [d[0] for d in cur.description]
                rows = cur.fetchall()
            conn.close()
            df = pd.DataFrame(rows, columns=cols)
            if not df.empty:
                _CACHE[tipo] = df
            return df.copy()
        except Exception as e:
            print(f"[ERRO] Falha ao carregar dados (aguas_andinas): {e}")
            return pd.DataFrame()

    tipo = tipo if tipo in SQLs else "macro"
    if tipo in _CACHE:
        return _CACHE[tipo].copy()

    query = SQLs[tipo]
    try:
        conn = pymysql.connect(**DB_CONFIG)
        with conn.cursor() as cur:
            cur.execute(query)
            cols = [d[0] for d in cur.description]
            rows = cur.fetchall()
        conn.close()
        df = pd.DataFrame(rows, columns=cols)
        # Não cachear DataFrames vazios — podem ser resultado de race condition
        # com o refresh (TRUNCATE + INSERT) da stored procedure
        if not df.empty:
            _CACHE[tipo] = df
        return df.copy()
    except Exception as e:
        print(f"[ERRO] Falha ao carregar dados ({tipo}): {e}")
        return pd.DataFrame()


def invalidar_cache(tipo: str = None):
    """Remove o cache para forçar recarga na próxima chamada.
    Se 'stats' for passado, invalida apenas o cache de stats_por_arquivo."""
    if tipo == "stats":
        _CACHE_STATS.clear()
    elif tipo:
        _CACHE.pop(tipo, None)
    else:
        _CACHE.clear()
        _CACHE_STATS.clear()


def carregar_status_aa() -> pd.DataFrame:
    """Carrega distribuição total de status de tabela_macros_aa (sem filtro de data)."""
    cache_key = "aa_status_dist"
    if cache_key in _CACHE:
        return _CACHE[cache_key].copy()
    try:
        conn = pymysql.connect(**DB_CONFIG_AA)
        with conn.cursor() as cur:
            cur.execute(SQL_AA_STATUS_DIST)
            cols = [d[0] for d in cur.description]
            rows = cur.fetchall()
        conn.close()
        df = pd.DataFrame(rows, columns=cols)
        if not df.empty:
            _CACHE[cache_key] = df
        return df.copy()
    except Exception as e:
        print(f"[ERRO] Falha ao carregar status AA: {e}")
        return pd.DataFrame()


def refresh_dashboard_macros_agg() -> bool:
    """Invalida o cache para forçar recarga na próxima leitura.
    (CPFL: sem tabela materializada, dados lidos diretamente.)
    """
    invalidar_cache("macro")
    return True


# ---------------------------------------------------------------------------
# Estatísticas por arquivo de staging
# Usa staging_import_rows para contar combos distintas por arquivo (correto e
# independente de quando o passo 02 rodou — antes o JOIN por data falhava se
# o processamento ocorria em dias diferentes do import).
# ---------------------------------------------------------------------------
_SQL_STATS_ARQUIVO = """
    SELECT
        si.filename                          AS arquivo,
        DATE(si.created_at)                  AS data_carga,
        si.rows_success                      AS cpfs_no_arquivo,
        COALESCE(cc.distinct_cpfs, 0)        AS cpfs_processados,
        0                                    AS ativos,
        0                                    AS inativos,
        COALESCE(cc.distinct_cpfs, 0)        AS cpfs_ineditos,
        COALESCE(cc.distinct_combos, 0)      AS ucs_ineditas,
        0                                    AS combos_processadas,
        0                                    AS combos_ativas,
        0                                    AS combos_inativas,
        0 AS ineditos_processados,
        0 AS ineditos_ativos,
        0 AS ineditos_inativos
    FROM staging_imports si
    LEFT JOIN (
        SELECT
            staging_id,
            COUNT(DISTINCT normalized_cpf) AS distinct_cpfs,
            COUNT(DISTINCT normalized_cpf, normalized_uc) AS distinct_combos
        FROM staging_import_rows
        WHERE validation_status = 'valid'
        GROUP BY staging_id
    ) cc ON cc.staging_id = si.id
    WHERE si.status = 'completed'
    ORDER BY si.created_at DESC
"""

# Status global de processamento das macros (não dependente de staging)
_SQL_MACROS_STATUS_GLOBAL = """
    SELECT
        SUM(IF(status NOT IN ('pendente','processando'), 1, 0)) AS combos_processadas,
        SUM(IF(status = 'ativo', 1, 0))  AS combos_ativas,
        SUM(IF(status = 'inativo', 1, 0)) AS combos_inativas,
        COUNT(*) AS total_macros
    FROM tabela_macros_cpfl
"""


def carregar_stats_por_arquivo() -> pd.DataFrame:
    """Retorna estatísticas de todos os arquivos de staging.
    Conta combos distintas por arquivo via staging_import_rows, e
    distribui proporcionalmente o status de processamento das macros.
    Cacheado em memória por _CACHE_STATS_TTL segundos.
    """
    cached = _CACHE_STATS.get("stats")
    if cached is not None:
        df_cached, ts = cached
        if time.time() - ts < _CACHE_STATS_TTL:
            return df_cached.copy()

    try:
        conn = pymysql.connect(**DB_CONFIG)
        with conn.cursor() as cur:
            # Per-file distinct combos
            cur.execute(_SQL_STATS_ARQUIVO)
            cols = [d[0] for d in cur.description]
            rows = cur.fetchall()

            # Global macro status
            cur.execute(_SQL_MACROS_STATUS_GLOBAL)
            global_row = cur.fetchone()
        conn.close()

        df = pd.DataFrame(rows, columns=cols)
        if df.empty:
            return df

        # Converte colunas numéricas (podem vir como Decimal do MySQL)
        for col in df.columns:
            if col not in ("arquivo", "data_carga"):
                df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0).astype(int)

        # Distribui os status globais proporcionalmente baseado em ucs_ineditas
        total_combos_all = int(df["ucs_ineditas"].sum())
        if total_combos_all > 0 and global_row:
            g_processadas = int(global_row[0] or 0)
            g_ativas = int(global_row[1] or 0)
            g_inativas = int(global_row[2] or 0)
            for col, g_val in [("combos_processadas", g_processadas),
                               ("combos_ativas", g_ativas),
                               ("combos_inativas", g_inativas)]:
                df[col] = (df["ucs_ineditas"] / total_combos_all * g_val).round(0).astype(int)

        if not df.empty:
            _CACHE_STATS["stats"] = (df, time.time())
        return df.copy()
    except Exception as e:
        print(f"[ERRO] carregar_stats_por_arquivo: {e}")
        return pd.DataFrame()


def refresh_dashboard_arquivos_agg() -> bool:
    """Invalida o cache de stats para forçar recarga na próxima leitura."""
    invalidar_cache("stats")
    return True


