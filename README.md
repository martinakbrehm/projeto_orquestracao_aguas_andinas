# projeto_orquestracao_aguas_andinas

Pipeline de orquestração end-to-end para automação da validação de contatos de clientes Águas Andinas. O sistema integra ingestão de arquivos CSV, processamento ETL, execução de macro de consulta via API, e exposição de métricas em dashboard analítico — tudo sobre um banco MySQL gerenciado na AWS RDS.

---

## Arquitetura

```
┌──────────────────────────────────────────────────────────────────────┐
│                          FONTES DE DADOS                             │
│  dados/bases/   ENTREGA BASE NOMBRE DIRECCION FECH NAC.txt           │
│                 ENTREGA CELULAR.txt                                   │
│                 ENTREGA CORREOv.txt                                  │
└──────────────────────┬───────────────────────────────────────────────┘
                       │
                       ▼
┌──────────────────────────────────────────────────────────────────────┐
│                    CAMADA DE INGESTÃO (ETL Load)                     │
│  01_importar_clientes_aa.py   — RUT, nome, sexo, data_nascimento     │
│                                 + staging_imports (controle)         │
│  02_importar_contatos_aa.py   — telefones + e-mails (enriquecimento) │
│  03_reimportar_enderecos_aa.py — direccion, comuna, region           │
└──────────────────────┬───────────────────────────────────────────────┘
                       │  tabela_macros_aa (status=pendente)
                       ▼
┌──────────────────────────────────────────────────────────────────────┐
│                    CAMADA DE ORQUESTRAÇÃO (Macro)                    │
│  executar_db.py   — consome lotes de pendentes, chama API de         │
│                     consulta, salva resultado no banco               │
└──────────────────────┬───────────────────────────────────────────────┘
                       │  tabela_macros_aa (status=telefone_validado|
                       │                          telefone_nao_validado)
                       ▼
┌──────────────────────────────────────────────────────────────────────┐
│                    CAMADA ANALÍTICA (Dashboard)                      │
│  Dashboard Dash/Plotly → http://127.0.0.1:8050                       │
│  Refresh automático: 08h e 17h (thread interno)                      │
└──────────────────────────────────────────────────────────────────────┘
```

---

## Modelo Relacional

**Banco:** `bd_Automacoes_time_dados_aguas_andinas` (MySQL 8, AWS RDS)

### Diagrama

```
staging_imports ─────────────────────────────────────────────────────┐
  id PK | filename | total_rows | rows_success | rows_failed          │
  status ENUM | created_at | started_at | finished_at                 │
       │                                                               │
       │  1:N (staging_id)                                            │
       ▼                                                               │
clientes ─────────────────────────────────────────────────────────────┤
  id PK | rut UNIQUE(8) | dv(1) | nome | sexo | data_nascimento       │
  staging_id FK → staging_imports                                     │
  data_criacao | data_update                                           │
       │                                                               │
       ├──────────────────────────────────────────────────────────────┤
       │  1:N                        1:N                   1:1        │
       ▼                             ▼                     ▼          │
enderecos             telefones             emails          │          │
  id PK                id PK                id PK           │          │
  cliente_id FK        cliente_id FK        cliente_id FK   │          │
  direccion            numero               endereco        │          │
  comuna               origem ENUM          origem ENUM     │          │
  region               staging_id FK ───────────────────────┘          │
  data_criacao         data_criacao         data_criacao               │
                                                                        │
       │                                                               │
       │  1:1 (UNIQUE)                                                 │
       ▼                                                               │
tabela_macros_aa ─────────────────────────────────────────────────────┘
  id PK | cliente_id FK (UNIQUE)
  resposta_id FK → respostas
  telefone_id FK → telefones (origem=validado)
  email_id FK    → emails    (origem=validado)
  status ENUM | extraido | data_extracao
  data_criacao | data_update

respostas
  id PK | mensagem | status

staging_import_rows
  id PK | staging_id FK | row_idx
  raw_rut | raw_nome | normalized_rut | normalized_dv
  validation_status ENUM | validation_message | processed_at
```

### Tabelas

#### `staging_imports`
Controla cada importação de arquivo. Criado ao início da carga; atualizado com totais ao final.

| Coluna | Descrição |
|--------|-----------|
| `filename` | Nome do arquivo importado (ex: `BASES ABRIL-2026`) |
| `rows_success` | Linhas processadas com sucesso |
| `rows_failed` | Linhas rejeitadas |
| `status` | `pending` → `processing` → `completed` / `failed` |

#### `clientes`
Um registro por RUT (identificador fiscal chileno). Inserção com `INSERT IGNORE` — o RUT é a chave de deduplicação.

| Coluna | Descrição |
|--------|-----------|
| `rut` | RUT sem DV, sem pontos, sem zeros à esquerda (ex: `12345678`) |
| `dv` | Dígito verificador: `0-9` ou `K` |
| `staging_id` | FK para `staging_imports` — identifica de qual importação o cliente veio |

#### `enderecos`
Endereço chileno do cliente. Um por cliente (`INSERT IGNORE` via `cliente_id`).

#### `telefones`
Todos os telefones do cliente, por origem. Chave única: `(cliente_id, numero, origem)`.

| `origem` | Descrição |
|----------|-----------|
| `enriquecimento` | Inserido na importação da base de contatos (arquivo `ENTREGA CELULAR.txt`) |
| `validado` | Retornado e confirmado pela macro em tempo de execução |

#### `emails`
Mesma estrutura de `telefones`. Origem `enriquecimento` vem de `ENTREGA CORREOv.txt`.

#### `tabela_macros_aa`
Uma linha por cliente (UNIQUE em `cliente_id`). Registra o status atual da validação pela macro.

| Coluna | Descrição |
|--------|-----------|
| `resposta_id` | FK → `respostas`; indica o cenário de retorno da API |
| `telefone_id` | FK → `telefones (origem=validado)` quando a macro retornou telefone |
| `email_id` | FK → `emails (origem=validado)` quando a macro retornou e-mail |
| `extraido` | `0` = dado ainda não consumido; `1` = já usado em alguma ação/envio |
| `data_extracao` | Timestamp de quando o dado foi consumido (gerenciado manualmente) |

**Ciclo de vida do status:**

```
pendente ──→ processando ──→ telefone_validado      (API retornou telefone)
                         └──→ telefone_nao_validado  (sem telefone, erro, inválido)
```

#### `respostas`
Catálogo dos cenários de retorno da macro:

| id | mensagem | status |
|----|----------|--------|
| 1 | Sucesso com telefone e e-mail | `telefone_validado` |
| 2 | Sucesso sem dados | `telefone_nao_validado` |
| 3 | Usuário já registrado | `telefone_nao_validado` |
| 4 | Falha de conexão / API | `telefone_nao_validado` |
| 5 | Aguardando processamento | `telefone_nao_validado` |
| 6 | Sucesso apenas com telefone | `telefone_validado` |
| 7 | Sucesso apenas com e-mail | `telefone_nao_validado` |
| 8 | Telefone inválido (normalização) | `telefone_nao_validado` |

---

## Dashboard

### Acesso

```
URL:    http://127.0.0.1:8050
Usuário: aguasandinas
Senha:   dashboard2026
```

### Iniciar

```powershell
python dashboard_macros/run_dashboard.py
```

### Seções

| Seção | Descrição |
|-------|-----------|
| **Resumo por data de processamento** | Total, com telefone e sem telefone agrupados por dia de execução da macro. Filtrável por mês e dia. |
| **Distribuição por status** | Contagem total de RUTs em cada status da fila (`pendente`, `processando`, `telefone_validado`, `telefone_nao_validado`). |
| **Distribuição por resposta** | Quantidade de RUTs por tipo de retorno da macro (cenários 1–8). |
| **Resultados por arquivo de staging** | Uma linha por importação: RUTs no banco, processados, pendentes, com/sem telefone. |

### Refresh automático

O dashboard atualiza os dados automaticamente **duas vezes por dia**, às **08h e às 17h**, via thread interna agendada (`_refresh_bg` em `dashboard.py`). O processo:

1. Executa `executar_refresh()` — limpa queries órfãs e recarrega dados no banco
2. Invalida o cache em memória (`loader.invalidar_cache()`)
3. Pré-aquece o cache com dados frescos para que a próxima requisição seja instantânea

O componente `dcc.Interval` do Dash dispara adicionalmente a cada **12 horas** no cliente, garantindo que uma aba aberta por mais de 12h também receba dados novos.

Para forçar um refresh manual sem reiniciar o servidor:

```powershell
python -m dashboard_macros.refresh_scheduler --once
```

---

## Setup

### 1. Credenciais

```powershell
cp config.example.py config.py
# Edite config.py com as credenciais do banco MySQL
```

`config.py` define `db_aguas_andinas()` — conexão ao banco AA (AWS RDS).

> `config.py` está no `.gitignore`. **Nunca versionar.**

### 2. Banco de dados

```powershell
python db_aguas_andinas/setup_database.py
```

Idempotente (`CREATE TABLE IF NOT EXISTS`). Aplica schema completo incluindo tabelas, índices, triggers e views.

### 3. Dependências

```powershell
pip install pymysql pandas dash dash-auth plotly
```

---

## Execução do Pipeline

### Etapa 1 — Importar clientes (base principal)

```powershell
python etl/load/aguas_andinas/01_importar_clientes_aa.py
```

Lê `dados/bases/ENTREGA BASE NOMBRE DIRECCION FECH NAC.txt`, cria registro em `staging_imports`, insere clientes com `INSERT IGNORE` (deduplicação por RUT) e vincula cada cliente ao `staging_id` da importação.

### Etapa 2 — Importar contatos (telefones + e-mails)

```powershell
python etl/load/aguas_andinas/02_importar_contatos_aa.py
```

Lê `ENTREGA CELULAR.txt` e `ENTREGA CORREOv.txt`. Aplica normalização de telefones antes de inserir.

**Normalização de telefones:**

| Dígitos | Ação |
|---------|------|
| 8 | Adiciona `9` na frente (`12345678` → `912345678`) |
| 9 | Mantém como está |
| outros | Descartado → `resposta_id=8`, status `telefone_nao_validado` |

### Etapa 3 — Reimportar endereços

```powershell
python etl/load/aguas_andinas/03_reimportar_enderecos_aa.py
```

Aplica limpeza completa em `comuna` e `region` (5 etapas): expansão de nomes truncados, remoção de nomes de região no campo de comuna, correção de truncamentos, normalização de espaços e pontuação.

### Etapa 4 — Rodar a macro

```powershell
# Processa lotes de 500 até zerar todos os pendentes
python macro/valida_dados_aguasandinas_v2.1/executar_db.py

# Opções
python executar_db.py --lotes 3          # máximo 3 lotes
python executar_db.py --tamanho 100      # lotes de 100 registros
python executar_db.py --pausa 2          # pausa entre requisições (default: 1s)
python executar_db.py --dry-run          # consulta API sem salvar no banco
```

A macro lê `pendente` de `tabela_macros_aa`, chama a API, interpreta o retorno e grava `resposta_id`, `status`, `telefone_id`, `email_id` de volta no banco.

---

## Controle de Extração

Os campos `extraido` e `data_extracao` em `tabela_macros_aa` são gerenciados **manualmente** após o consumo dos dados validados. A macro e o ETL **nunca** os alteram.

```sql
-- Buscar dados ainda não consumidos
SELECT c.rut, c.nome, t.numero AS telefone, e.endereco AS email
FROM tabela_macros_aa tm
JOIN clientes c ON c.id = tm.cliente_id
LEFT JOIN telefones t ON t.id = tm.telefone_id
LEFT JOIN emails    e ON e.id = tm.email_id
WHERE tm.extraido = 0
  AND tm.status = 'telefone_validado';

-- Marcar como consumido após uso
UPDATE tabela_macros_aa
SET extraido = 1, data_extracao = NOW()
WHERE id IN (...);
```

---

## Estrutura do Projeto

```
projeto_orquestracao_aguas_andinas/
│
├── config.py                        # Credenciais — NÃO versionado (.gitignore)
├── config.example.py                # Template público
│
├── db_aguas_andinas/
│   ├── schema.sql                   # DDL completo: tabelas, índices, triggers, views
│   └── setup_database.py            # Aplica schema via pymysql (idempotente)
│
├── dados/
│   ├── bases/                       # Arquivos de entrada — NÃO versionados
│   └── resultados/                  # CSVs de resultado da macro
│
├── etl/
│   ├── load/aguas_andinas/
│   │   ├── 01_importar_clientes_aa.py   # Ingestão RUT + staging_id
│   │   ├── 02_importar_contatos_aa.py   # Telefones + e-mails
│   │   └── 03_reimportar_enderecos_aa.py # Endereços com limpeza
│   └── transformation/macro_aa/
│       └── interpretar_resposta_aa.py   # Regras: retorno API → (resposta_id, status)
│
├── macro/
│   └── valida_dados_aguasandinas_v2.1/
│       ├── executar_db.py           # Runner integrado ao banco (CLI)
│       ├── main.py                  # GUI tkinter (uso manual)
│       └── core/                    # Extrator, Validador
│
└── dashboard_macros/
    ├── run_dashboard.py             # Entry point: inicia servidor na porta 8050
    ├── dashboard.py                 # App Dash: layout, callbacks, refresh automático
    ├── data/loader.py               # SQL + cache em memória (TTL: refresh 2x/dia)
    └── service/orchestrator.py      # Filtros e agregações para o resumo diário
```

---

## Decisões de Engenharia

| Decisão | Justificativa |
|---------|---------------|
| `INSERT IGNORE` em `clientes` com dedup por RUT | Permite reimportar o mesmo arquivo sem duplicatas |
| `staging_id` em `clientes` | Rastreia de qual importação cada cliente veio; permite queries corretas por staging |
| 1 registro por cliente em `tabela_macros_aa` (UNIQUE em `cliente_id`) | Simplifica leitura e evita estados contraditórios; a macro sempre sobrescreve o resultado mais recente |
| `extraido` / `data_extracao` fora do ciclo da macro | Desacopla o controle de consumo do processamento; permite reuso seguro dos dados |
| Cache em memória no dashboard | Isola a leitura analítica da carga transacional; latência de resposta <1ms após aquecimento |
| Refresh às 08h e 17h via thread interna | Dados sempre atualizados nos principais turnos sem depender de agendador externo (Task Scheduler / cron) |
| Normalização de telefones centralizada | Regra única aplicada tanto na importação quanto na macro; evita divergências |

---

## Git

```powershell
git add -A
git commit -m "tipo: descrição"
git push origin main
```


---

## Arquitetura

```
┌─────────────────────────────────────────────────────────────────────┐
│                        FONTES DE DADOS                              │
│  Arquivos CSV (CPF, UC, nome)  →  dados/                            │
└───────────────────────┬─────────────────────────────────────────────┘
                        │
                        ▼
┌─────────────────────────────────────────────────────────────────────┐
│                      CAMADA DE INGESTÃO (ETL Load)                  │
│  01_staging_import_cpfl.py   — hash de arquivo, dedup, staging      │
│  02_processar_staging_cpfl.py — normalização CPF/UC, upsert         │
│                                 clientes + cliente_uc               │
└───────────────────────┬─────────────────────────────────────────────┘
                        │  tabela_macros_cpfl (status=pendente)
                        ▼
┌─────────────────────────────────────────────────────────────────────┐
│                      CAMADA DE ORQUESTRAÇÃO                         │
│  03_buscar_lote_cpfl.py  — prioridade pendente > reprocessar,       │
│                            marca status=processando, exporta CSV    │
│  executar_cpfl.py        — runner Selenium headless (portal GMP)    │
│  04_processar_retorno_cpfl.py — interpreta ATIVO+ERRO, insere       │
│                                 resultado, arquiva lote             │
└───────────────────────┬─────────────────────────────────────────────┘
                        │  tabela_macros_cpfl (status=consolidado|excluido|reprocessar)
                        ▼
┌─────────────────────────────────────────────────────────────────────┐
│                      CAMADA ANALÍTICA                               │
│  dashboard_macros_agg (tabela materializada)                        │
│  dashboard_arquivos_agg / dashboard_cobertura_agg                   │
│  Dashboard Dash/Plotly  →  http://127.0.0.1:8050                    │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Modelo de Dados

**Banco:** `bd_Automacoes_time_dados_cpfl` (MySQL 8, AWS RDS)

```
clientes ─────────────────────────────────────────────────┐
  id PK | cpf UNIQUE | nome | data_nascimento              │
                                                           │
cliente_uc ───────────────────────────────────────────────┤
  id PK | cliente_id FK | uc UNIQUE(cliente_id, uc)        │
                                                           │
tabela_macros_cpfl ───────────────────────────────────────┘
  id PK | cliente_id FK | cliente_uc_id FK                 
  resposta_id FK | pn | status ENUM | extraido             
  data_criacao | data_update | data_extracao               

respostas          → catálogo de respostas do portal GMP
telefones          → 1:N por cliente
enderecos          → 1:N por cliente/UC
staging_imports    → controle de importações (idempotência por hash)
staging_import_rows → linhas brutas com status de validação
```

**Ciclo de vida do status em `tabela_macros_cpfl`:**

```
pendente → processando → consolidado   (titularidade confirmada)
                       → reprocessar   (instalação inativa / erro temporário)
                       → excluido      (CPF/UC não pertence ao titular)
```

O modelo é **append-only**: cada ciclo insere um novo registro de resultado preservando o histórico completo de consultas por CPF+UC.

---

## Estrutura do Projeto

```
projeto_orquestracao_cpfl/
│
├── config.py                        # Credenciais — NÃO versionado (.gitignore)
├── config.example.py                # Template público de credenciais
│
├── db_cpfl/
│   ├── schema.sql                   # DDL completo: tabelas, índices, triggers
│   └── setup_database.py            # Aplica schema via pymysql (idempotente)
│
├── dados/                           # CSVs de entrada — NÃO versionados
│
├── etl/
│   ├── extraction/macro_cpfl/
│   │   └── 03_buscar_lote_cpfl.py   # Extração priorizada do banco → CSV
│   ├── load/macro_cpfl/
│   │   ├── 01_staging_import_cpfl.py    # Ingestão com dedup por hash de arquivo
│   │   ├── 02_processar_staging_cpfl.py # Validação, normalização, upsert
│   │   └── 04_processar_retorno_cpfl.py # Carga dos resultados da macro
│   └── transformation/macro_cpfl/
│       └── interpretar_resposta_cpfl.py # Regras: ATIVO+ERRO → (resposta_id, status, pn)
│
├── macro/
│   ├── dados_cpfl/                  # Arquivos de lote em trânsito — NÃO versionados
│   └── macro_cpfl/
│       ├── painel.py                # GUI tkinter: painel liga/desliga com log
│       ├── executar_automatico.py   # Orquestrador: loop extract→macro→load
│       ├── PAINEL.bat
│       ├── EXECUTAR.bat
│       └── valida_pn_gmp-main/      # Pacote Selenium — portal GMP
│           ├── executar_cpfl.py     # Entry point CLI (headless, sem tkinter)
│           ├── config.py            # Importa credenciais do config.py raiz
│           ├── core/                # PortalGMP, Validador, GerenciadorDados
│           ├── interface/           # UI standalone (uso manual)
│           └── utils/               # Scraping helpers, notificador
│
└── dashboard_macros/
    ├── dashboard.py                 # App Dash: layout, callbacks, autenticação
    ├── data/loader.py               # SQL + cache em memória (sem TTL)
    ├── service/orchestrator.py      # Filtros, agregações, build de tabelas
    └── refresh_scheduler.py         # Scheduler: refresh das tabelas materializadas
```

---

## Setup

### 1. Credenciais

```powershell
cp config.example.py config.py
# Edite config.py com as credenciais do banco MySQL e do portal GMP
```

`config.py` define:
- `db_cpfl()` — conexão ao banco CPFL (AWS RDS)
- `GMP_USUARIOS` — lista de usuários do portal `gmp.cpfl.com.br`
- `gmp_usuario(indice)` — helper para rotação de contas

> `config.py` está no `.gitignore`. **Nunca versionar.**

### 2. Banco de Dados

```powershell
python db_cpfl/setup_database.py
```

O script é idempotente (`CREATE TABLE IF NOT EXISTS`, `INSERT ... ON DUPLICATE KEY UPDATE`).

### 3. Dependências

```powershell
pip install pymysql pandas dash dash-auth plotly
pip install selenium python-dotenv  # para a macro
```

---

## Execução do Pipeline

### Etapa 1 — Importar arquivos CSV

```powershell
python etl/load/macro_cpfl/01_staging_import_cpfl.py
```

Faz hash dos arquivos em `dados/`, ignora reimportações, popula `staging_import_rows`.

### Etapa 2 — Processar staging

```powershell
python etl/load/macro_cpfl/02_processar_staging_cpfl.py
```

Normaliza CPF (LPAD 11 dígitos), valida UC, faz upsert em `clientes` e `cliente_uc`, enfileira registros `pendente` em `tabela_macros_cpfl`.

**Otimização de índices (bulk insert):** antes de inserir em massa na `tabela_macros_cpfl`, o script dropa os 6 índices secundários da tabela para evitar que o MySQL atualize cada índice a cada INSERT. Ao final do bulk, recria todos os índices de uma vez — isso é ordens de magnitude mais rápido para cargas de milhões de registros. Os índices dropados/recriados são os mesmos definidos no `schema.sql`:

| Índice | Colunas |
|--------|---------|
| `idx_cpfl_macros_status_data` | (status, data_update, cliente_id) |
| `idx_cpfl_macros_cliente_data` | (cliente_id, data_update) |
| `idx_cpfl_macros_extraido_status` | (extraido, status, data_update) |
| `idx_cpfl_macros_resposta` | (resposta_id) |
| `idx_cpfl_macros_data_extracao` | (data_extracao) |
| `idx_cpfl_macros_pn` | (pn) |

Esse processo é idempotente: se o script for interrompido, na próxima execução ele tenta dropar (ignora se não existem) e ao final recria.

### Etapa 3 — Rodar a macro (ciclo contínuo)

**Pelo painel (recomendado):**

```powershell
cd macro\macro_cpfl
PAINEL.bat
```

**Pelo terminal:**

```powershell
cd macro\macro_cpfl
python executar_automatico.py --tamanho 500 --pausa 60
```

| Parâmetro | Padrão | Descrição |
|-----------|--------|-----------|
| `--tamanho` | 500 | Registros por lote |
| `--pausa` | 60 | Pausa (s) entre ciclos |
| `--max-erros` | 3 | Interrompe após N erros consecutivos |
| `--continuar` | — | Retoma lote existente sem limpeza |

O orquestrador executa automaticamente:
1. `03_buscar_lote_cpfl.py` — extrai lote priorizado e marca `processando`
2. `executar_cpfl.py` — Selenium consulta cada CPF+UC no portal GMP
3. `04_processar_retorno_cpfl.py` — interpreta resultados, insere em `tabela_macros_cpfl`, reverte registros não processados para `reprocessar`

### Etapa 4 — Dashboard

```powershell
python -m dashboard_macros
```

Acesse em [http://127.0.0.1:8050](http://127.0.0.1:8050). O dashboard lê de tabelas materializadas (`dashboard_macros_agg`, `dashboard_arquivos_agg`) atualizadas pelo scheduler interno.

---

## Decisões de Engenharia

| Decisão | Justificativa |
|---------|---------------|
| Modelo append-only em `tabela_macros_cpfl` | Preserva histórico completo; permite auditoria e reprocessamento sem perda de dados |
| Staging com hash de arquivo | Garante idempotência na ingestão — reimportar o mesmo CSV não gera duplicatas |
| Status `processando` explícito | Permite detectar e reverter lotes interrompidos (crash recovery) |
| Tabelas materializadas no dashboard | Desacopla leitura analítica da carga transacional; latência de query <1ms |
| Credenciais centralizadas em `config.py` | Fonte única de verdade; `.gitignore` protege todos os projetos dependentes |
| Runner CLI separado da GUI | `executar_cpfl.py` pode ser chamado por qualquer orquestrador; GUI é opcional |

---

## Git

```powershell
git remote set-url origin https://github.com/martinakbrehm/projeto_cpfl.git

git add -A
git commit -m "tipo: descrição"
git push
```

---

## Águas Andinas

### Banco: `bd_Automacoes_time_dados_aguas_andinas`

#### Modelo de Dados

```
clientes ─────────────────────────────────────────────────────────────┐
  id PK | rut UNIQUE | dv | nome | sexo | data_nascimento             │
                                                                       │
enderecos ────────────────────────────────────────────────────────────┤
  id PK | cliente_id FK | direccion | comuna | region                  │
                                                                       │
telefones ────────────────────────────────────────────────────────────┤
  id PK | cliente_id FK | numero | staging_id FK                       │
  origem ENUM('enriquecimento','validado')                             │
  UNIQUE (cliente_id, numero, origem)                                  │
                                                                       │
emails ───────────────────────────────────────────────────────────────┤
  id PK | cliente_id FK | endereco | staging_id FK                     │
  origem ENUM('enriquecimento','validado')                             │
  UNIQUE (cliente_id, endereco, origem)                                │
                                                                       │
tabela_macros_aa ─────────────────────────────────────────────────────┘
  id PK | cliente_id FK UNIQUE | resposta_id FK | status ENUM
  telefone_id FK | email_id FK
  extraido TINYINT(1) DEFAULT 0 | data_extracao DATETIME DEFAULT NULL
  data_criacao | data_update

respostas         → catálogo dos 7 cenários de retorno da macro
staging_imports   → controle de importações (idempotência por hash)
staging_import_rows → linhas brutas com status de validação
```

#### Ciclo de vida do status em `tabela_macros_aa`

| Status | Significado |
|--------|-------------|
| `pendente` | ainda não processado pela macro |
| `processando` | em andamento |
| `telefone_validado` | SUCESSO=1 com telefone retornado (com ou sem e-mail) |
| `telefone_nao_validado` | SUCESSO=1 sem telefone, usuário já registrado, falha ou telefone inválido |

Mapeamento `respostas`:

| id | mensagem | status |
|----|----------|--------|
| 1 | Sucesso com telefone e e-mail | `telefone_validado` |
| 2 | Sucesso sem dados | `telefone_nao_validado` |
| 3 | Usuário já registrado | `telefone_nao_validado` |
| 4 | Falha de conexão / API | `telefone_nao_validado` |
| 5 | Aguardando processamento | `telefone_nao_validado` |
| 6 | Sucesso apenas com telefone | `telefone_validado` |
| 7 | Sucesso apenas com e-mail | `telefone_nao_validado` |
| 8 | Telefone invalido | `telefone_nao_validado` |

#### Controle de extração (`extraido` / `data_extracao`)

- `extraido = 0`, `data_extracao = NULL` → **padrão ao inserir**; dado ainda não consumido
- `extraido = 1`, `data_extracao = <datetime>` → dado já consumido/enviado

**Regras:**
- A macro e o ETL **nunca** tocam nesses campos
- São gerenciados **manualmente** após consumo dos dados
- Padrão para buscar apenas dados não consumidos:

```sql
SELECT * FROM tabela_macros_aa
WHERE extraido = 0
  AND status = 'telefone_validado'
```

- Para marcar como consumido:

```sql
UPDATE tabela_macros_aa
SET extraido = 1, data_extracao = NOW()
WHERE id IN (...)
```

#### Origens em `telefones` e `emails`

| origem | descrição |
|--------|-----------|
| `enriquecimento` | inserido pelo pipeline a partir da base histórica |
| `validado` | confirmado pela macro (arquivo `_RESULTADO.csv`) |

#### Normalização de Telefones

Aplicada automaticamente no pipeline e na macro:

| Dígitos | Ação |
|---------|------|
| 8 | Adiciona `9` na frente (ex: `12345678` → `912345678`) |
| 9 | Mantém como está |
| outros | Descartado (`resposta_id=8`, status `telefone_nao_validado`) |

Função centralizada: `etl/load/aguas_andinas/limpeza_enderecos.py` → `normalizar_telefone()`

#### Limpeza de Endereços

Módulo centralizado: `etl/load/aguas_andinas/limpeza_enderecos.py`

Aplica 5 etapas sobre `comuna` e `region`:
1. Expansão de regiões truncadas (ex: `METROPOLIT` → `METROPOLITANA DE SANTIAGO`)
2. Nulifica nomes de região no campo `comuna`
3. Corrige truncamentos de prefixo (lista estática)
4. Normaliza espaços múltiplos e pontuação
5. Remove ponto final, letra extra no fim, corrige palavras coladas

#### Execução do Pipeline AA

```powershell
# 1. Importar base de clientes
python etl/load/aguas_andinas/01_importar_clientes_aa.py

# 2. Importar contatos (telefones + e-mails) — normalização automática de telefones
python etl/load/aguas_andinas/02_importar_contatos_aa.py

# 3. Reimportar/atualizar endereços com limpeza completa
python etl/load/aguas_andinas/03_reimportar_enderecos_aa.py

# 4. Processar retorno da macro (CSVs _RESULTADO.csv)
python etl/load/aguas_andinas/04_processar_retorno_aa.py
```
