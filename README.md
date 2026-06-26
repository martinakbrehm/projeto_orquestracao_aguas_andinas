# Pipeline de Orquestração — Águas Andinas

> Pipeline ETL end-to-end para validação e enriquecimento de contatos de clientes da **Águas Andinas** (Chile), integrando ingestão em batch, processamento via API externa, modelagem relacional em MySQL 8 (AWS RDS) e dashboard analítico com tabelas materializadas e cache em memória.

---

## Visão Geral

O pipeline processa bases de clientes fornecidas pela Águas Andinas — identificados pelo **RUT chileno** (equivalente ao CPF) — e valida seus contatos (telefone e e-mail) consultando a API proprietária da empresa. Cada execução atualiza o estado de processamento no banco em tempo real, desacopla o consumo dos dados validados via flag de extração e disponibiliza métricas operacionais em um dashboard interno.

**Escala atual:** +305 mil clientes processados, com 117 mil extrações na última execução.

---

## Stack

| Camada | Tecnologias |
|--------|-------------|
| Linguagem | Python 3.12 |
| Banco de dados | MySQL 8 — AWS RDS (`us-east-1`) |
| Driver | PyMySQL |
| Camada analítica | Dash + Plotly + Dash-Auth |
| Orquestração | Python nativo — batch runner CLI com recuperação automática |

---

## Arquitetura

```
┌─────────────────────────────────────────────────────────────────────────┐
│                           FONTES DE DADOS                               │
│   Arquivos .txt fornecidos pelo cliente                                 │
│   (RUT, nome, sexo, data_nascimento, endereço, telefones, e-mails)      │
└───────────────────────────────┬─────────────────────────────────────────┘
                                │  Ingestão em batch
                                ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                     CAMADA DE INGESTÃO  (ETL — Load)                    │
│                                                                         │
│  01_importar_clientes_aa.py    — dedup por RUT via INSERT IGNORE        │
│                                   staging_id rastreia a origem          │
│  02_importar_contatos_aa.py    — telefones + e-mails com normalização   │
│  03_reimportar_enderecos_aa.py — endereços com pipeline de limpeza      │
│                                   em 5 etapas (comuna / region)         │
└───────────────────────────────┬─────────────────────────────────────────┘
                                │  tabela_macros_aa → status = pendente
                                ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                    CAMADA DE ORQUESTRAÇÃO  (Macro / API)                │
│                                                                         │
│  executar_db.py — consome lotes de pendentes via stored procedure,      │
│                   chama API Águas Andinas, interpreta cada cenário       │
│                   de resposta e persiste resultado no banco              │
│                                                                         │
│  Crash recovery: falhas retornam a pendente automaticamente             │
└───────────────────────────────┬─────────────────────────────────────────┘
                                │  status = telefone_validado
                                │          telefone_nao_validado
                                ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                    CAMADA DE EXTRAÇÃO  (Exportação)                     │
│                                                                         │
│  extraction/extrair_pendentes.py — query por extraido = 0,              │
│                                    gera CSV no formato do cliente,       │
│                                    marca extraido = 1 + data_extracao   │
└───────────────────────────────┬─────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                    CAMADA ANALÍTICA  (Dashboard)                        │
│                                                                         │
│  Leitura exclusiva de tabelas materializadas                            │
│  Cache em memória sem TTL — invalidado apenas no refresh                │
│  Refresh automático: 08h e 17h via thread interna                       │
│  http://127.0.0.1:8052                                                  │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## Modelo de Dados

**Banco:** `bd_Automacoes_time_dados_aguas_andinas` — MySQL 8, AWS RDS

```
staging_imports
  id PK | filename | total_rows | rows_success | rows_failed
  status ENUM(pending → processing → completed / failed)
  created_at | started_at | finished_at
        │ 1:N
        ▼
clientes  ────────────────────────────────────────────────────────────┐
  id PK | rut UNIQUE CHAR(8) | dv CHAR(1)                             │
  nome | sexo | data_nascimento                                        │
  staging_id FK → staging_imports                                      │
        │                                                              │
        ├──────────────┬──────────────────────────────────────────────┤
        │ 1:N          │ 1:N                   │ 1:N                  │
        ▼              ▼                        ▼                     │
enderecos         telefones                  emails                   │
  direccion         numero                    endereco                │
  comuna            origem ENUM               origem ENUM             │
  region            staging_id FK             staging_id FK           │
                    UNIQUE(cliente_id,         UNIQUE(cliente_id,     │
                           numero, origem)            endereco,       │
                                                      origem)         │
        │ 1:1 (UNIQUE cliente_id)                                      │
        ▼                                                              │
tabela_macros_aa ─────────────────────────────────────────────────────┘
  id PK | cliente_id FK UNIQUE
  resposta_id FK → respostas
  telefone_id FK → telefones (origem = validado)
  email_id    FK → emails    (origem = validado)
  status ENUM(pendente | processando | telefone_validado | telefone_nao_validado)
  extraido TINYINT(1) DEFAULT 0    ← flag de consumo — nunca alterado pela macro
  data_extracao DATETIME           ← timestamp do consumo — gerenciado pela extração
  data_criacao | data_update

respostas
  id PK | mensagem | status   ← catálogo dos 8 cenários de retorno da API
```

---

## Estratégia de Indexação

A indexação foi projetada para os três padrões de acesso dominantes: leitura da fila de pendentes (orquestração), escrita em bulk (ingestão) e leitura analítica (dashboard).

### `tabela_macros_aa`

```sql
UNIQUE KEY uk_aa_macros_cliente   (cliente_id)
INDEX idx_aa_macros_status_data   (status, data_update, cliente_id)
INDEX idx_aa_macros_cliente_data  (cliente_id, data_update)
INDEX idx_aa_macros_resposta      (resposta_id)
INDEX idx_aa_macros_telefone      (telefone_id)
INDEX idx_aa_macros_email         (email_id)
INDEX idx_aa_macros_extraido      (extraido)
```

| Índice | Padrão atendido |
|--------|-----------------|
| `uk_aa_macros_cliente` | Garante 1 estado por cliente; acelera `ON DUPLICATE KEY UPDATE` da macro |
| `(status, data_update, cliente_id)` | Cobre index para a `VIEW view_aa_macros_pendentes`: filtra por `status = 'pendente'` e ordena por `data_update ASC` — evita full table scan na fila |
| `(cliente_id, data_update)` | Consultas temporais por cliente (histórico de processamento) |
| `(extraido)` | Filtro rápido na extração: `WHERE extraido = 0 AND status = 'telefone_validado'` |
| `(telefone_id)`, `(email_id)` | Joins de validação: busca o contato associado ao resultado da macro |

### `telefones` e `emails`

```sql
UNIQUE KEY ux_telefone_cliente_numero_origem (cliente_id, numero, origem)
INDEX idx_telefones_cliente  (cliente_id)
INDEX idx_telefones_numero   (numero)
INDEX idx_telefones_origem   (origem)
INDEX idx_telefones_staging  (staging_id)
```

A chave única composta `(cliente_id, numero, origem)` serve dois propósitos: impede duplicatas e permite `INSERT IGNORE` idempotente — o mesmo número pode existir como `enriquecimento` e como `validado` sem conflito.

### `staging_imports` e `staging_import_rows`

```sql
INDEX idx_staging_status      (status)
INDEX idx_staging_created_at  (created_at)
INDEX idx_staging_rows_normrut (normalized_rut)
```

O índice em `normalized_rut` acelera o lookup do RUT normalizado durante a ingestão, quando o script de importação verifica se o cliente já existe antes de inserir.

---

## Lógica de Orquestração

### Fila de Processamento

A orquestração é baseada em **state machine** na `tabela_macros_aa`. Cada cliente tem exatamente um registro (UNIQUE em `cliente_id`), e o status evolui de forma linear:

```
pendente ──→ processando ──→ telefone_validado
                         └──→ telefone_nao_validado
```

A macro nunca deleta registros — apenas atualiza o estado, preservando auditabilidade completa.

### Leitura da Fila — Stored Procedure

O runner lê pendentes via `get_aa_macros_batch(batch_size)`, que internamente consulta a view `view_aa_macros_pendentes`:

```sql
-- View: garante o registro mais recente por RUT em caso de reimportação
CREATE VIEW view_aa_macros_pendentes AS
SELECT vm.* FROM (
  SELECT tm.*, c.rut,
         ROW_NUMBER() OVER (
           PARTITION BY c.rut
           ORDER BY tm.data_update DESC, tm.id DESC
         ) AS rn
  FROM tabela_macros_aa tm
  JOIN clientes c ON c.id = tm.cliente_id
  WHERE tm.status = 'pendente'
) vm WHERE vm.rn = 1;
```

A window function `ROW_NUMBER() OVER PARTITION BY rut` garante que, se o mesmo RUT existir em múltiplos registros (reimportações), apenas o mais recente entre na fila — sem processamento duplicado.

### Ciclo do Runner (`executar_db.py`)

```
para cada lote de N pendentes:
    1. Lê lote via get_aa_macros_batch(N)
    2. Marca status = 'processando' (isolamento — evita que outro processo
       leia o mesmo lote em execução paralela)
    3. Para cada cliente no lote:
         a. Chama API Águas Andinas com o RUT
         b. Interpreta resposta → (resposta_id, status, telefone?, email?)
         c. Se retornou telefone: INSERT em telefones (origem=validado)
                                  INSERT em emails    (origem=validado) se houver
         d. UPDATE tabela_macros_aa: resposta_id, status, telefone_id, email_id
    4. Registros não processados (timeout/erro): voltam a pendente
    5. Pausa configurável entre lotes
    6. Interrompe quando não há mais pendentes
```

### Crash Recovery

Registros marcados como `processando` que não forem concluídos (queda do processo, timeout de API) **não ficam presos**. Na próxima execução, o runner reverte `processando → pendente` antes de buscar o próximo lote, garantindo que nenhum registro fique em estado inconsistente indefinidamente.

### Interpretação de Resposta

O módulo `interpretar_resposta_aa.py` encapsula todo o mapeamento `resposta_da_API → (resposta_id, status)`:

| Cenário | `resposta_id` | `status` |
|---------|--------------|---------|
| Sucesso com telefone e e-mail | 1 | `telefone_validado` |
| Sucesso sem dados | 2 | `telefone_nao_validado` |
| Usuário já registrado | 3 | `telefone_nao_validado` |
| Falha de conexão / API | 4 | `telefone_nao_validado` |
| Aguardando processamento | 5 | `telefone_nao_validado` |
| Sucesso apenas com telefone | 6 | `telefone_validado` |
| Sucesso apenas com e-mail | 7 | `telefone_nao_validado` |
| Telefone inválido | 8 | `telefone_nao_validado` |

Centralizar essa lógica no módulo de transformação garante que a macro e qualquer reprocessamento futuro apliquem exatamente as mesmas regras.

---

## Dashboard Analítico

### Arquitetura do Dashboard

O dashboard segue o padrão **read-from-materialized + in-memory cache**, desacoplando completamente a leitura analítica da carga transacional:

```
Dash (browser)
    │  HTTP request
    ▼
Callbacks (dashboard.py)
    │  chama
    ▼
Orchestrator (service/orchestrator.py)
    │  build_dashboard_data() aplica filtros em pandas
    ▼
Loader (data/loader.py)
    │  verifica _CACHE (dict em memória)
    │  cache hit  → retorna cópia do DataFrame instantaneamente
    │  cache miss → SELECT nas tabelas materializadas → popula cache
    ▼
MySQL (dashboard_macros_agg / dashboard_status_agg / dashboard_staging_agg)
```

**O banco nunca é consultado diretamente em tempo de request** — apenas quando o cache está vazio (primeira carga ou após refresh).

### Tabelas Materializadas

As três tabelas abaixo são populadas pela stored procedure `sp_refresh_dashboard_agg()` e jamais recebem escrita pelo pipeline transacional:

#### `dashboard_macros_agg`
Granularidade: **dia × status × mensagem de resposta**

```sql
SELECT DATE(tm.data_update), tm.status, r.mensagem, COUNT(*)
FROM tabela_macros_aa tm
LEFT JOIN respostas r ON r.id = tm.resposta_id
WHERE tm.status NOT IN ('pendente', 'processando')
GROUP BY DATE(tm.data_update), tm.status, r.mensagem
```

Permite filtrar o dashboard por data (dia individual ou mês inteiro via prefixo `mes:YYYY-MM`) sem tocar na tabela transacional.

#### `dashboard_status_agg`
Granularidade: **status total** (todos os clientes, sem filtro de data)

```sql
SELECT tm.status, COUNT(*) FROM tabela_macros_aa tm GROUP BY tm.status
```

Alimenta o card de distribuição global de status no dashboard.

#### `dashboard_staging_agg`
Granularidade: **arquivo de importação**

```sql
SELECT si.filename, DATE(si.created_at),
       COUNT(DISTINCT c.id),
       SUM(IF(tm.status NOT IN ('pendente','processando'), 1, 0)),
       SUM(IF(tm.status = 'pendente', 1, 0)),
       SUM(IF(tm.status = 'telefone_validado', 1, 0)),
       SUM(IF(tm.status = 'telefone_nao_validado', 1, 0))
FROM staging_imports si
JOIN clientes c ON c.staging_id = si.id
JOIN tabela_macros_aa tm ON tm.cliente_id = c.id
WHERE si.status = 'completed'
GROUP BY si.id, si.filename
```

Permite rastrear a taxa de sucesso por arquivo de importação — indispensável para auditar qual base de clientes gerou mais validações.

### Estratégia de Cache

```python
_CACHE: dict = {}   # chave: tipo de dado → valor: DataFrame
                    # sem TTL — vive durante o processo
                    # invalidado explicitamente no refresh
```

O cache não tem TTL proposital: os dados só mudam quando a procedure de refresh é executada. Usar TTL causaria recargas desnecessárias entre os refreshes agendados. O padrão de invalidação é:

```
refresh executado → invalidar_cache() → próxima request popula o cache
```

O pré-aquecimento após o refresh (`carregar_dados()` chamado imediatamente após invalidar) garante que a primeira requisição pós-refresh também seja instantânea.

### Refresh Agendado

```python
# Thread interna em dashboard.py
schedule.every().day.at("08:00").do(executar_refresh)
schedule.every().day.at("17:00").do(executar_refresh)

def executar_refresh():
    loader.refresh_dashboard_macros_agg()   # CALL sp_refresh_dashboard_agg()
    loader.invalidar_cache()                # limpa o dict em memória
    loader.carregar_dados()                 # pré-aquece o cache
```

Adicionalmente, um `dcc.Interval` no cliente Dash dispara a cada 12 horas, garantindo que abas abertas por longos períodos também recebam dados atualizados.

Para forçar refresh manual sem reiniciar o servidor:

```bash
python -m dashboard_macros.refresh_scheduler --once
```

### Painéis

| Painel | Fonte | Descrição |
|--------|-------|-----------|
| Resumo por data | `dashboard_macros_agg` | Total, com telefone e sem telefone por dia de processamento; filtrável por mês ou dia |
| Distribuição de status | `dashboard_status_agg` | Contagem total em cada estado da fila |
| Distribuição por resposta | `dashboard_macros_agg` | Quebra pelos 8 cenários de retorno da API |
| Resultados por staging | `dashboard_staging_agg` | Uma linha por importação: clientes, processados, pendentes, com/sem telefone |

---

## Controle de Extração

Os campos `extraido` e `data_extracao` implementam um **padrão de consumo idempotente**: qualquer camada downstream pode verificar o que já foi extraído sem risco de reprocessamento.

```
extraido = 0, data_extracao = NULL   → disponível para extração
extraido = 1, data_extracao = <ts>   → já consumido; não reextrair
```

**Invariante crítica:** a macro e o ETL **nunca** alteram esses campos. São responsabilidade exclusiva da camada de exportação (`extraction/extrair_pendentes.py`). Esse desacoplamento permite que o pipeline de validação evolua independentemente do mecanismo de entrega dos dados.

```sql
-- Buscar dados disponíveis
SELECT c.rut, c.dv, c.nome, t.numero AS telefone, e.endereco AS email
FROM tabela_macros_aa tm
JOIN  clientes  c ON c.id = tm.cliente_id
LEFT JOIN telefones t ON t.id = tm.telefone_id
LEFT JOIN emails    e ON e.id = tm.email_id
WHERE tm.status   = 'telefone_validado'
  AND tm.extraido = 0;

-- Marcar como consumido após extração
UPDATE tabela_macros_aa
SET extraido = 1, data_extracao = NOW()
WHERE id IN (...);
```

---

## Decisões de Engenharia

| Decisão | Justificativa |
|---------|---------------|
| `INSERT IGNORE` + dedup por RUT | Idempotência na ingestão — reimportar o mesmo arquivo não gera duplicatas |
| `staging_id` em `clientes`, `telefones` e `emails` | Linhagem de dados: rastreia de qual importação cada registro veio sem joins extras |
| UNIQUE em `cliente_id` na `tabela_macros_aa` | Um estado por cliente; a macro sempre sobrescreve o resultado mais recente sem ambiguidade |
| State machine com status `processando` | Isolamento de lotes em processamento paralelo — evita que dois runners peguem o mesmo registro |
| `extraido` desacoplado da macro | O pipeline de validação não conhece o downstream de consumo; extração é responsabilidade de outra camada |
| Tabelas materializadas + stored procedure | Queries analíticas com GROUP BY em 300 k+ registros são pré-computadas; dashboard faz apenas `SELECT *` |
| Cache em memória sem TTL | Dados mudam apenas no refresh agendado — TTL causaria recargas desnecessárias |
| Pré-aquecimento do cache pós-refresh | Primeira requisição após atualização também é instantânea |
| Refresh às 08h/17h via thread interna | Dados atualizados nos turnos operacionais sem dependência de agendador externo |
| `origem ENUM('enriquecimento', 'validado')` em telefones/emails | A mesma tabela suporta contatos da base histórica e os confirmados pela API — UNIQUE composto impede duplicatas entre origens |
| Normalização de telefones centralizada | Regra única aplicada na ingestão e na macro — adiciona prefixo `9` em 8 dígitos, descarta inválidos com `resposta_id = 8` |
| Limpeza de endereços em 5 etapas | Expande truncamentos, remove nomes de região em campo de comuna, corrige prefixos, normaliza espaços — tratamento robusto de dados operacionais sujos |
| Window function na view de pendentes | `ROW_NUMBER() OVER PARTITION BY rut` garante que reimportações não gerem processamento duplicado |

---

## Estrutura do Projeto

```
projeto_orquestracao_aguas_andinas/
│
├── config.py                          # Credenciais — NÃO versionado (.gitignore)
├── config.example.py                  # Template público
├── requirements.txt
│
├── db_aguas_andinas/
│   ├── schema.sql                     # DDL completo: tabelas, índices, triggers,
│   │                                  # views, stored procedures
│   └── setup_database.py              # Aplica schema via PyMySQL (idempotente)
│
├── etl/
│   ├── load/aguas_andinas/
│   │   ├── 01_importar_clientes_aa.py
│   │   ├── 02_importar_contatos_aa.py
│   │   └── 03_reimportar_enderecos_aa.py
│   └── transformation/macro_aa/
│       └── interpretar_resposta_aa.py
│
├── macro/
│   └── valida_dados_aguasandinas_v2.1/
│       ├── executar_db.py             # Runner CLI com crash recovery
│       ├── main.py                    # Interface tkinter (uso manual)
│       └── core/                      # HTTP client, validador de resposta
│
├── extraction/
│   └── extrair_pendentes.py           # Exporta validados → CSV; marca extraido = 1
│
├── dashboard_macros/
│   ├── run_dashboard.py               # Entry point — porta 8052
│   ├── dashboard.py                   # Layout Dash, callbacks, refresh agendado
│   ├── data/loader.py                 # Leitura das agg tables + cache em memória
│   ├── refresh_scheduler.py           # Chama sp_refresh_dashboard_agg()
│   └── service/orchestrator.py        # Filtros e agregações para os painéis
│
└── dados/                             # NÃO versionado (.gitignore)
    ├── bases/                         # Arquivos de entrada do cliente
    ├── formato/                       # Template CSV de entrega
    └── resultados/                    # CSVs de extração gerados
```

---

## Setup

### 1. Credenciais

```bash
cp config.example.py config.py
# Preencha com as credenciais do MySQL (AWS RDS)
```

`config.py` está no `.gitignore` — nunca versionar.

### 2. Banco de dados

```bash
python db_aguas_andinas/setup_database.py
```

Idempotente — aplica todo o schema: tabelas, índices, triggers, views, stored procedures e tabelas materializadas.

### 3. Dependências

```bash
pip install -r requirements.txt
```

---

## Execução do Pipeline

```bash
# 1. Ingestão de clientes
python etl/load/aguas_andinas/01_importar_clientes_aa.py

# 2. Ingestão de contatos (normalização automática de telefones)
python etl/load/aguas_andinas/02_importar_contatos_aa.py

# 3. Ingestão de endereços com limpeza
python etl/load/aguas_andinas/03_reimportar_enderecos_aa.py

# 4. Validação via API (processa todos os pendentes em lotes)
python macro/valida_dados_aguasandinas_v2.1/executar_db.py
python executar_db.py --lotes 3       # máximo 3 lotes por execução
python executar_db.py --tamanho 200   # registros por lote (default: 500)
python executar_db.py --pausa 2       # segundos entre requisições (default: 1)
python executar_db.py --dry-run       # consulta API sem persistir no banco

# 5. Exportação dos validados não consumidos
python extraction/extrair_pendentes.py
```

---

## Dashboard

```
URL:      http://127.0.0.1:8052
Usuário:  aguasandinas
```

```bash
python -m dashboard_macros
```
