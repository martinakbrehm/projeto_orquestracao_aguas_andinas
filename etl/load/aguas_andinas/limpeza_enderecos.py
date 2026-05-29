"""
limpeza_enderecos.py
=====================
Módulo centralizado de limpeza de endereços para o pipeline Águas Andinas.
Consolida as 5 etapas de limpeza aplicadas ao arquivo base:

  Etapa 1 — expansão de regiões truncadas e validação contra 16 regiões oficiais
  Etapa 2 — nulifica nomes de região no campo comuna; corrige truncamentos/typos
  Etapa 3 — corrige truncamentos de cidades por prefixo (lista estática)
  Etapa 4 — normaliza espaços múltiplos e pontuação (G.CARREÑO → G. CARREÑO)
  Etapa 5 — remove ponto final, letra extra no fim, corrige palavras coladas

Uso:
    from limpeza_enderecos import limpar_region, limpar_comuna, normalizar_rut
"""

import re
import unicodedata

# ---------------------------------------------------------------------------
# Regiões oficiais do Chile (16)
# ---------------------------------------------------------------------------
REGIOES_VALIDAS = frozenset({
    "METROPOLITANA DE SANTIAGO",
    "DE VALPARAISO",
    "DEL BIOBIO",
    "DE LA ARAUCANIA",
    "DEL LIBERTADOR GRAL. BERNARDO O'HIGGINS",
    "DE LOS LAGOS",
    "DE COQUIMBO",
    "DE ANTOFAGASTA",
    "DE LOS RIOS",
    "DE TARAPACA",
    "DE ARICA Y PARINACOTA",
    "DE MAGALLANES Y LA ANTARTICA CHILENA",
    "DE AYSEN DEL GRAL. CARLOS IBANEZ DEL CAMPO",
    "DEL MAULE",
    "DE NUBLE",
    "DE ATACAMA",
    # Com acentos (como vêm do REGION_MAP)
    "DE VALPARAÍSO",
    "DEL BIOBÍO",
    "DE LA ARAUCANÍA",
    "DE LOS RÍOS",
    "DE TARAPACÁ",
    "DE MAGALLANES Y LA ANTÁRTICA CHILENA",
    "DE AYSÉN DEL GRAL. CARLOS IBÁÑEZ DEL CAMPO",
    "DE ÑUBLE",
})

# Regiões truncadas no arquivo fonte → nome completo
REGION_MAP: dict[str, str] = {
    "METROPOLIT": "METROPOLITANA DE SANTIAGO",
    "DE VALPARA": "DE VALPARAÍSO",
    "DEL BIOBIO": "DEL BIOBÍO",
    "DE LA ARAU": "DE LA ARAUCANÍA",
    "DEL LIBERT": "DEL LIBERTADOR GRAL. BERNARDO O'HIGGINS",
    "DE LOS LAG": "DE LOS LAGOS",
    "DE COQUIMB": "DE COQUIMBO",
    "DE ANTOFAG": "DE ANTOFAGASTA",
    "DE LOS RIO": "DE LOS RÍOS",
    "DE TARAPAC": "DE TARAPACÁ",
    "DE ARICA Y": "DE ARICA Y PARINACOTA",
    "DE MAGALLA": "DE MAGALLANES Y LA ANTÁRTICA CHILENA",
    "DE AYSEN D": "DE AYSÉN DEL GRAL. CARLOS IBÁÑEZ DEL CAMPO",
}

REGION_INVALIDA = frozenset({"CHILE", "VIÑA DEL MAR", "PUENTE ALTO"})

# ---------------------------------------------------------------------------
# Prefixos de nome de região que aparecem indevidamente no campo comuna
# (devem ser nulificados)
# ---------------------------------------------------------------------------
_PREFIXOS_REGIAO: frozenset[str] = frozenset({
    "REGION METROPOLITANA", "REGION METROPOLITAN", "REGION METROPOLITA",
    "REGION METROPOLI", "REGION METROPOL", "REGION METROPO", "REGION METRO",
    "REGION METROP", "REGION METR", "REGION MET", "REGION ME",
    "METROPOLITANA DE SANTIAGO", "METROPOLITANA DE SANTIAG",
    "MAGALLANES Y LA ANTARTICA CHILENA",
    "MAGALLANES Y LA ANTARTICA CHILEN",
    "MAGALLANES Y LA ANTARTICA CHILE",
    "MAGALLANES Y LA ANTARTICA CHIL",
    "MAGALLANES Y LA ANTARTICA CHI",
    "MAGALLANES Y LA ANTARTICA CH",
    "MAGALLANES Y LA ANTARTICA C",
    "MAGALLANES Y LA ANTARTICA",
    "MAGALLANES Y LA ANTARTIC",
    "MAGALLANES Y LA ANTARTI",
    "MAGALLANES Y LA ANTART",
    "MAGALLANES Y LA ANTAR",
    "MAGALLANES Y LA ANTA",
    "MAGALLANES Y LA ANT",
    "MAGALLANES Y LA AN",
    "MAGALLANES Y LA A",
    "MAGALLANES Y LA",
    "MAGALLANES Y L",
    "ARICA Y PARINACOTA",
    "ARICA Y PARINACOT",
    "ARICA Y PARINACO",
    "ARICA Y PARINAC",
    "ARICA Y PARINA",
    "ARICA Y PARIN",
    "ARICA Y PARI",
})

# ---------------------------------------------------------------------------
# Correções de comunas: chave = valor sujo em MAIÚSCULAS → correto ou None
# Consolida as etapas 2, 3 e 5 (correções estáticas)
# ---------------------------------------------------------------------------
CORRECOES_COMUNA: dict[str, str | None] = {
    # ── Regiões no campo comuna → nulificar ──────────────────────────────────
    "REGION METROPOLITANA":   None,
    "ARICA Y PARINACOTA":     None,

    # ── Etapa 2: truncamentos e typos conhecidos ─────────────────────────────
    "ESTACION CENTRA":        "ESTACION CENTRAL",
    "ESTACION CENTR":         "ESTACION CENTRAL",
    "ESTACION CENT":          "ESTACION CENTRAL",
    "ESTACION CEN":           "ESTACION CENTRAL",
    "ESTACION CE":            "ESTACION CENTRAL",
    "ESTACION C":             "ESTACION CENTRAL",
    "DIEGO DE ALMAGR":        "DIEGO DE ALMAGRO",
    "DIEGO DE ALMA":          "DIEGO DE ALMAGRO",
    "DIEGO DE AL":            "DIEGO DE ALMAGRO",
    "TORRES DEL PAIN":        "TORRES DEL PAINE",
    "TORRES DEL PAI":         "TORRES DEL PAINE",
    "TORRES D":               "TORRES DEL PAINE",
    "POZO ALMONT":            "POZO ALMONTE",
    "POZO ALM":               "POZO ALMONTE",
    "PANGUIPULL":             "PANGUIPULLI",
    "LOS MUERMO":             "LOS MUERMOS",
    "PICHIDANGU":             "PICHIDANGUI",
    "PICHIDEGU":              "PICHIDEGUA",
    "SANTO DOMING":           "SANTO DOMINGO",
    "ANTOFAGAST":             "ANTOFAGASTA",
    "ANTOFAG":                "ANTOFAGASTA",
    "ANTOF":                  "ANTOFAGASTA",
    "MIRAFLORES ALT":         "MIRAFLORES ALTO",
    "MIRAFLORES AL":          "MIRAFLORES ALTO",
    "MIRAFORES":              "MIRAFLORES",
    "MIRAFLORE":              "MIRAFLORES",
    "REÑACAALTO":             "REÑACA ALTO",
    "SANTAJULIA":             "SANTA JULIA",
    "NUEVAGRANADILLA":        "NUEVA GRANADILLA",
    "NUÑOA":                  "ÑUÑOA",
    "PLATYA ANCHA":           "PLAYA ANCHA",
    "MELIPILÑLA":             "MELIPILLA",
    "CHORRILOS":              "CHORRILLOS",
    "DEPARTAMETO":            "DEPARTAMENTO",
    "FORESTAL FOIRESTAL ALTO":"FORESTAL ALTO",
    "FOREST AL BAJO":         "FORESTAL BAJO",

    # ── Etapa 3: truncamentos de prefixo (estáticos) ─────────────────────────
    "LOS LAGO":               "LOS LAGOS",
    "LOS LAG":                "LOS LAGOS",
    "HIJUEL":                 "HIJUELAS",
    "HIJUELA":                "HIJUELAS",
    "SAN FERNAND":            "SAN FERNANDO",
    "PLACILLA DE PENUE":      "PLACILLA DE PENUELAS",
    "PLACILLA DE PENU":       "PLACILLA DE PENUELAS",
    "LINARE":                 "LINARES",
    "PAILL":                  "PAILLACO",
    "OSORN":                  "OSORNO",
    "LA SE":                  "LA SERENA",
    "LA SER":                 "LA SERENA",
    "LA SERE":                "LA SERENA",
    "LA SEREN":               "LA SERENA",
    "O'HIGG":                 "O'HIGGINS",
    "O'HIGGI":                "O'HIGGINS",
    "O'HIGGIN":               "O'HIGGINS",
    "CONCEP":                 "CONCEPCION",
    "RIO BUEN":               "RIO BUENO",
    "LAGO R":                 "LAGO RANCO",
    "LAGO RAN":               "LAGO RANCO",
    "CHILLAN VIE":            "CHILLAN VIEJO",
    "CHILLAN V":              "CHILLAN VIEJO",
    "CASAB":                  "CASABLANCA",
    "SAGRADA F":              "SAGRADA FAMILIA",
    "COQUIMB":                "COQUIMBO",
    "VALLE":                  "VALLENAR",
    "VALPAR":                 "VALPARAISO",
    "VALPA":                  "VALPARAISO",
    "VALPARA":                "VALPARAISO",
    "VALPARAI":               "VALPARAISO",
    "LA LI":                  "LA LIGUA",
    "LA LIGU":                "LA LIGUA",
    "POBL. P. HURTA":         "POBL. P. HURTADO",
    "POBL. P. HURTAD":        "POBL. P. HURTADO",
    "VILLA AL":               "VILLA ALEMANA",
    "SANTA CLA":              "SANTA CLARA",
    "LOS ANGELE":             "LOS ANGELES",
    "LOS ANG":                "LOS ANGELES",
    "VINA DEL M":             "VINA DEL MAR",
    "VINA DEL MA":            "VINA DEL MAR",
    "VINA D":                 "VINA DEL MAR",
    "VINA":                   "VINA DEL MAR",
    "PEDRO AGUI":             "PEDRO AGUIRRE CERDA",
    "PADRE LAS CAS":          "PADRE LAS CASAS",
    "VICTORI":                "VICTORIA",
    "LONCOCH":                "LONCOCHE",
    "ACHUPALLA":              "ACHUPALLAS",
    "LAUTA":                  "LAUTARO",
    "PITRUFQ":                "PITRUFQUEN",
    "ALTO HOS":               "ALTO HOSPICIO",
    "ALTO HOSP":              "ALTO HOSPICIO",
    "SAN E":                  "SAN ESTEBAN",
    "CALAM":                  "CALAMA",
    "RECRE":                  "RECREO",
    "MIRADOR DE RENA":        "MIRADOR DE RENACA",

    # ── Etapa 5: palavras coladas, S faltando ─────────────────────────────────
    "GLORIASNAVALES":         "GLORIAS NAVALES",
    "BIOBIO":                 "BIO BIO",
    "CHORRILLOS":             "CHORRILLOS",

    # ── Etapa 5: letra extra no fim (bloco/unidade) → remove (None = remoção feita dinamicamente)
    "REÑACA ALTO C":          "REÑACA ALTO",
    "REÑACA ALTO B":          "REÑACA ALTO",
    "REÑACA ALTO O":          "REÑACA ALTO",
    "REÑACA ALTO E":          "REÑACA ALTO",
    "REÑACA ALTO K":          "REÑACA ALTO",
    "ACHUPALLAS A":           "ACHUPALLAS",
    "ACHUPALLAS B":           "ACHUPALLAS",
    "MIRAFLORES ALTO B":      "MIRAFLORES ALTO",
    "PLAYA ANCHA D":          "PLAYA ANCHA",
    "PLAYA ANCHA B":          "PLAYA ANCHA",
    "SAN VICENTE T":          "SAN VICENTE",
    "TEMUCO P":               "TEMUCO",
    "CHANARAL A":             "CHANARAL",

    # ── Não são comunas → nulificar ───────────────────────────────────────────
    "CONDOMINIO":             None,
    "CONDOMINI":              None,
    "CONDOMINIU":             None,
    "CONDOMIN":               None,
    "DEPARTAMENTO":           None,
    "DEPARTAMEN":             None,
    "DEPARTAMENT":            None,
    "DEPARTAME":              None,
    "DEPARTAM":               None,
    "DEPTO":                  None,
}

# ---------------------------------------------------------------------------
# Padrão de commune suja
# ---------------------------------------------------------------------------
_RE_DIGIT      = re.compile(r"[0-9]")
_INICIO_INVALIDO = frozenset(".#-(/,")
_RE_ESPACOS    = re.compile(r" {2,}")
_RE_PONTO_LETRA = re.compile(r"\.([A-Za-zÀ-ÿÑñ])")


def _norm_sem_acento(s: str) -> str:
    """Versão ASCII uppercase sem acentos, para comparação com CORRECOES_COMUNA."""
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    return s.upper()


def _normalizar_espaco(v: str) -> str:
    """Colapsa espaços duplos e adiciona espaço após ponto colado a letra."""
    v = _RE_ESPACOS.sub(" ", v).strip()
    v = _RE_PONTO_LETRA.sub(r". \1", v)
    return v.strip()


# ---------------------------------------------------------------------------
# API pública
# ---------------------------------------------------------------------------

def limpar_region(val: str) -> str | None:
    """
    Limpa o campo region:
    - Expande abreviações truncadas (ex: 'METROPOLIT' → 'METROPOLITANA DE SANTIAGO')
    - Nulifica valores que não são regiões chilenas válidas
    """
    v = (val or "").strip()
    if not v:
        return None
    v = REGION_MAP.get(v, v)
    if v in REGION_INVALIDA:
        return None
    if v not in REGIOES_VALIDAS:
        return None
    return v


def limpar_comuna(val: str) -> str | None:
    """
    Limpa o campo comuna aplicando todas as 5 etapas:
    1. Validação básica (dígitos, chars inválidos, comprimento)
    2. Normalização de espaços e pontuação
    3. Remoção de ponto final
    4. Correção por mapa estático (regiões no campo errado, typos, truncamentos)
    5. Prefixos de nomes de região → nulificar
    """
    v = (val or "").strip()
    if not v or len(v) < 3:
        return None
    if _RE_DIGIT.search(v):
        return None
    if v[0] in _INICIO_INVALIDO:
        return None

    # Etapa 4: normaliza espaços e pontuação
    v = _normalizar_espaco(v)

    # Etapa 5a: remove ponto(s) no final
    v_sem_ponto = v.rstrip(".")
    if len(v_sem_ponto) >= 3:
        v = v_sem_ponto

    # Revalida comprimento após normalização
    if not v or len(v) < 3:
        return None

    # Etapas 2+3+5: aplica mapa de correções (compara sem acentos)
    chave = _norm_sem_acento(v)
    if chave in CORRECOES_COMUNA:
        return CORRECOES_COMUNA[chave]  # pode ser None (nulificar)

    # Etapa 2: prefixos de nomes de região → nulificar
    if chave in _PREFIXOS_REGIAO:
        return None

    return v


def normalizar_rut(val: str) -> str | None:
    """Normaliza RUT chileno: remove pontos/traços, retorna só os dígitos sem zeros à esquerda."""
    v = str(val or "").strip().replace(".", "").replace("-", "")
    v = v.split()[0] if v else ""
    if not v or not v.isdigit():
        return None
    return v.lstrip("0") or "0"


def normalizar_telefone(val: str) -> str | None:
    """
    Normaliza número de telefone chileno:
    - 8 dígitos -> adiciona '9' na frente (ex: '12345678' -> '912345678')
    - 9 dígitos -> mantém como está
    - outros comprimentos -> None (inválido, descartar)
    """
    ds = re.sub(r"\D", "", str(val or ""))
    if len(ds) == 8:
        return "9" + ds
    if len(ds) == 9:
        return ds
    return None
