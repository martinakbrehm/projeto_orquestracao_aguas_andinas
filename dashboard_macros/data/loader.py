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

# Queries nas tabelas materializadas (populadas por sp_refresh_dashboard_agg)
SQL_AA = "SELECT dia, status, mensagem, qtd FROM dashboard_macros_agg ORDER BY dia DESC"

SQL_AA_STATUS_DIST = "SELECT status, qtd FROM dashboard_status_agg ORDER BY qtd DESC"

SQL_AA_STAGING = """
    SELECT arquivo, data_carga, clientes_no_banco, processados,
           pendentes, com_telefone, sem_telefone
    FROM dashboard_staging_agg
    ORDER BY data_carga DESC
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


def _chamar_refresh_procedure() -> bool:
    """Executa sp_refresh_dashboard_agg no banco e invalida o cache local."""
    try:
        conn = pymysql.connect(**DB_CONFIG_AA, autocommit=True)
        with conn.cursor() as cur:
            cur.execute("CALL sp_refresh_dashboard_agg()")
        conn.close()
        invalidar_cache()
        return True
    except Exception as e:
        print(f"[ERRO] Falha ao executar sp_refresh_dashboard_agg: {e}")
        return False


def refresh_dashboard_macros_agg() -> bool:
    """Reroda a procedure de refresh e invalida o cache."""
    return _chamar_refresh_procedure()


def refresh_dashboard_arquivos_agg() -> bool:
    """Reroda a procedure de refresh e invalida o cache."""
    return _chamar_refresh_procedure()


def carregar_stats_por_arquivo() -> pd.DataFrame:
    """Stub — não usado no projeto AA. Retorna DataFrame vazio."""
    return pd.DataFrame()


