# =============================================================================
# config.example.py  –  Template de credenciais
# Copie este arquivo para config.py e preencha com os valores reais.
# =============================================================================

# -----------------------------------------------------------------------------
# Banco de DESTINO  –  pipeline operacional
# -----------------------------------------------------------------------------
DB_DESTINO_HOST     = "seu-host.rds.amazonaws.com"
DB_DESTINO_PORT     = 3306
DB_DESTINO_USER     = "usuario"
DB_DESTINO_PASSWORD = "senha"
DB_DESTINO_DATABASE = "bd_Automacoes_time_dadosV2"

# -----------------------------------------------------------------------------
# Banco de ORIGEM  –  controle_bases (fonte de clientes/neo)
# -----------------------------------------------------------------------------
DB_ORIGEM_HOST     = "seu-host.rds.amazonaws.com"
DB_ORIGEM_PORT     = 3306
DB_ORIGEM_USER     = "usuario"
DB_ORIGEM_PASSWORD = "senha"
DB_ORIGEM_DATABASE = "controle_bases"


def db_destino(**kwargs) -> dict:
    """Config do banco de destino (bd_Automacoes_time_dadosV2)."""
    return dict(
        host=DB_DESTINO_HOST,
        port=DB_DESTINO_PORT,
        user=DB_DESTINO_USER,
        password=DB_DESTINO_PASSWORD,
        database=DB_DESTINO_DATABASE,
        charset="utf8mb4",
        **kwargs,
    )


def db_origem(**kwargs) -> dict:
    """Config do banco de origem (controle_bases)."""
    return dict(
        host=DB_ORIGEM_HOST,
        port=DB_ORIGEM_PORT,
        user=DB_ORIGEM_USER,
        password=DB_ORIGEM_PASSWORD,
        database=DB_ORIGEM_DATABASE,
        charset="utf8mb4",
        **kwargs,
    )


# -----------------------------------------------------------------------------
# Banco CONTATUS  –  bd_contatus (enriquecimento endereço/telefone)
# -----------------------------------------------------------------------------
DB_CONTATUS_HOST     = "seu-host.rds.amazonaws.com"
DB_CONTATUS_PORT     = 3306
DB_CONTATUS_USER     = "usuario"
DB_CONTATUS_PASSWORD = "senha"
DB_CONTATUS_DATABASE = "bd_contatus"


def db_contatus(**kwargs) -> dict:
    """Config do banco Contatus (bd_contatus)."""
    return dict(
        host=DB_CONTATUS_HOST,
        port=DB_CONTATUS_PORT,
        user=DB_CONTATUS_USER,
        password=DB_CONTATUS_PASSWORD,
        database=DB_CONTATUS_DATABASE,
        charset="utf8mb4",
        **kwargs,
    )


# -----------------------------------------------------------------------------
# Banco CPFL  –  bd_Automacoes_time_dados_cpfl
# -----------------------------------------------------------------------------
DB_CPFL_HOST     = "seu-host.rds.amazonaws.com"
DB_CPFL_PORT     = 3306
DB_CPFL_USER     = "usuario"
DB_CPFL_PASSWORD = "senha"
DB_CPFL_DATABASE = "bd_Automacoes_time_dados_cpfl"


def db_cpfl(**kwargs) -> dict:
    """Config do banco CPFL (bd_Automacoes_time_dados_cpfl)."""
    return dict(
        host=DB_CPFL_HOST,
        port=DB_CPFL_PORT,
        user=DB_CPFL_USER,
        password=DB_CPFL_PASSWORD,
        database=DB_CPFL_DATABASE,
        charset="utf8mb4",
        **kwargs,
    )


# -----------------------------------------------------------------------------
# Banco ÁGUAS ANDINAS  –  bd_aguas_andinas (enriquecimento)
# -----------------------------------------------------------------------------
DB_AGUAS_ANDINAS_HOST     = "seu-host.rds.amazonaws.com"
DB_AGUAS_ANDINAS_PORT     = 3306
DB_AGUAS_ANDINAS_USER     = "usuario"
DB_AGUAS_ANDINAS_PASSWORD = "senha"
DB_AGUAS_ANDINAS_DATABASE = "bd_Automacoes_time_dados_aguas_andinas"


def db_aguas_andinas(**kwargs) -> dict:
    """Config do banco Águas Andinas (bd_aguas_andinas)."""
    return dict(
        host=DB_AGUAS_ANDINAS_HOST,
        port=DB_AGUAS_ANDINAS_PORT,
        user=DB_AGUAS_ANDINAS_USER,
        password=DB_AGUAS_ANDINAS_PASSWORD,
        database=DB_AGUAS_ANDINAS_DATABASE,
        charset="utf8mb4",
        **kwargs,
    )


# -----------------------------------------------------------------------------
# Credenciais GMP  –  Portal CPFL (macro Selenium)
# Adicione quantos usuários precisar.
# -----------------------------------------------------------------------------
GMP_USUARIOS = [
    {"usuario": "cpf_usuario1", "senha": "senha1"},
    {"usuario": "cpf_usuario2", "senha": "senha2"},
]

GMP_USUARIO_PADRAO = GMP_USUARIOS[0]


def gmp_usuario(indice: int = 0) -> dict:
    """Retorna as credenciais GMP para o índice informado (padrão: 0)."""
    return GMP_USUARIOS[indice % len(GMP_USUARIOS)]
