"""
refresh_scheduler.py — Águas Andinas

O projeto AA não usa tabelas materializadas via stored procedures.
executar_refresh() é mantido como no-op para compatibilidade com dashboard.py.
"""

import logging

log = logging.getLogger("refresh_scheduler")


def executar_refresh() -> bool:
    """No-op para AA: não há stored procedures de refresh neste projeto."""
    log.info("refresh_scheduler: nada a fazer (projeto AA sem tabelas materializadas)")
    return True
