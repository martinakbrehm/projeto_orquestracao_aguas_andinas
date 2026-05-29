"""
interpretar_resposta_aa.py
==========================
Transformation: interpreta a resposta da macro Águas Andinas.

A macro salva um CSV com as colunas:
  RUT | DV | TELEFONE_VALIDADO | EMAIL_VALIDADO | SUCESSO | ERRO

Mapeamento para tabela_macros_aa:

  SUCESSO | TELEFONE_VALIDADO | EMAIL_VALIDADO | resposta_id | status
  --------+------------------+----------------+-------------+---------------------
     1    |     preenchido   |   preenchido   |      1      | telefone_validado
     1    |     preenchido   |     vazio      |      6      | telefone_validado
     1    |       vazio      |   preenchido   |      7      | telefone_nao_validado
     1    |       vazio      |     vazio      |      2      | telefone_nao_validado
     0    |        —         |       —        |      3      | telefone_nao_validado  (usuarioRegistrado)
     0    |        —         |       —        |      4      | pendente               (falha conexão/API → retentar)
     0    |        —         |       —        |      5      | pendente               (outros / desconhecido)
1    |   inválido (pres.)|     —          |      8      | telefone_nao_validado

Chamado por:
  etl/load/aguas_andinas/04_processar_retorno_aa.py
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Fragmentos de ERRO (lower-case) que indicam usuário já registrado
# ---------------------------------------------------------------------------
_ERROS_USUARIO_REGISTRADO = [
    "usuarioregistrado",
    "usuario registrado",
    "ya registrado",
    "já registrado",
]

# Fragmentos que indicam falha de conexão/API (deve retentar)
_ERROS_CONEXAO = [
    "falha de conexao",
    "falha de conexão",
    "timeout",
    "connection",
    "connectionerror",
    "httperror",
    "requestexception",
]


def interpretar(
    sucesso: int | str,
    telefone: str | None,
    email: str | None,
    erro: str | None,
) -> tuple[int, str]:
    """
    Interpreta uma linha do CSV resultado e retorna (resposta_id, novo_status).

    Parâmetros
    ----------
    sucesso  : 1 = sucesso, 0 = falha
    telefone : valor de TELEFONE_VALIDADO (vazio/None = sem telefone)
    email    : valor de EMAIL_VALIDADO    (vazio/None = sem e-mail)
    erro     : valor de ERRO              (vazio/None = sem erro)

    Retorna
    -------
    (resposta_id: int, novo_status: str)
        Valores prontos para INSERT/UPDATE em tabela_macros_aa.
    """
    tem_tel   = bool(telefone and str(telefone).strip())
    tem_email = bool(email    and str(email).strip())
    sucesso_i = int(sucesso) if str(sucesso).strip().isdigit() else 0

    # Normalização: 8 dígitos -> prepend '9'; 9 dígitos -> keep; outros -> inválido
    def _normalize_candidate(s: str):
        import re
        ds = re.sub(r"\D", "", str(s or ""))
        if len(ds) == 8:
            return '9' + ds
        if len(ds) == 9:
            return ds
        return None

    if sucesso_i == 1:
        # Se a macro reportou telefone, valide formato segundo as regras
        if tem_tel:
            normalized = _normalize_candidate(telefone)
            if not normalized:
                    # keep resposta_id 8, but use status telefone_nao_validado to match 'no phone found'
                    return (8, "telefone_nao_validado")
        if tem_tel and tem_email:
            return (1, "telefone_validado")    # Sucesso com telefone e e-mail
        if tem_tel:
            return (6, "telefone_validado")    # Sucesso apenas com telefone
        if tem_email:
            return (7, "telefone_nao_validado") # Sucesso apenas com e-mail
        return (2, "telefone_nao_validado")     # Sucesso sem dados

    # SUCESSO = 0 — analisa mensagem de erro
    erro_lower = str(erro or "").lower().strip()

    if any(frag in erro_lower for frag in _ERROS_USUARIO_REGISTRADO):
        return (3, "telefone_nao_validado")    # Usuário já registrado

    if any(frag in erro_lower for frag in _ERROS_CONEXAO):
        return (4, "pendente")                 # Falha conexão → retentar

    return (5, "pendente")                     # Desconhecido → retentar
