import sys
import time
from pathlib import Path

import pymysql
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from config import db_aguas_andinas  # noqa: E402

DB_CONFIG_AA = db_aguas_andinas()

_CACHE: dict = {}        # cache por tipo {'macro': df} — sem TTL, vive durante o processo
_CACHE_STATS: dict = {}  # cache para stats_por_arquivo / cobertura
_CACHE_STATS_TTL = 3600  # segundos (1 hora)

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

SQL_AA_STAGING = """
    SELECT
        si.filename                                                    AS arquivo,
        DATE(si.created_at)                                            AS data_carga,
        COUNT(DISTINCT c.id)                                           AS clientes_no_banco,
        SUM(IF(tm.status NOT IN ('pendente','processando'), 1, 0))     AS processados,
        SUM(IF(tm.status = 'pendente', 1, 0))                          AS pendentes,
        SUM(IF(tm.status = 'telefone_validado', 1, 0))                 AS com_telefone,
        SUM(IF(tm.status = 'telefone_nao_validado', 1, 0))             AS sem_telefone
    FROM staging_imports si
    JOIN clientes c ON c.staging_id = si.id
    JOIN tabela_macros_aa tm ON tm.cliente_id = c.id
    WHERE si.status = 'completed'
    GROUP BY si.id, si.filename, si.created_at, si.rows_success
    ORDER BY si.created_at DESC
"""



def carregar_dados(tipo: str = "aguas_andinas") -> pd.DataFrame:
    """Carrega dados da tabela_macros_aa.

    Resultado é cacheado em memória (sem TTL — vive durante o processo).
    """
    cache_key = "aguas_andinas"
    if cache_key in _CACHE:
        return _CACHE[cache_key].copy()
    try:
        conn = pymysql.connect(**DB_CONFIG_AA)
        with conn.cursor() as cur:
            cur.execute(SQL_AA)
            cols = [d[0] for d in cur.description]
            rows = cur.fetchall()
        conn.close()
        df = pd.DataFrame(rows, columns=cols)
        if not df.empty:
            _CACHE[cache_key] = df
        return df.copy()
    except Exception as e:
        print(f"[ERRO] Falha ao carregar dados: {e}")
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


def carregar_staging_aa() -> pd.DataFrame:
    """Carrega estatísticas por arquivo de staging para Águas Andinas."""
    cache_key = "aa_staging"
    if cache_key in _CACHE:
        return _CACHE[cache_key].copy()
    try:
        conn = pymysql.connect(**DB_CONFIG_AA)
        with conn.cursor() as cur:
            cur.execute(SQL_AA_STAGING)
            cols = [d[0] for d in cur.description]
            rows = cur.fetchall()
        conn.close()
        df = pd.DataFrame(rows, columns=cols)
        for col in ["clientes_no_banco", "com_telefone",
                    "sem_telefone", "pendentes", "processados"]:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0).astype(int)
        if not df.empty:
            _CACHE[cache_key] = df
        return df.copy()
    except Exception as e:
        print(f"[ERRO] Falha ao carregar staging AA: {e}")
        return pd.DataFrame()


def refresh_dashboard_macros_agg() -> bool:
    """Invalida o cache para forçar recarga na próxima leitura."""
    invalidar_cache("aguas_andinas")
    return True


def refresh_dashboard_arquivos_agg() -> bool:
    """Invalida o cache de staging para forçar recarga na próxima leitura."""
    invalidar_cache("aa_staging")
    return True


def carregar_stats_por_arquivo() -> pd.DataFrame:
    """Stub — não usado no projeto AA. Retorna DataFrame vazio."""
    return pd.DataFrame()


