# Instrucoes de Uso — Projeto Orquestracao Aguas Andinas

## Requisitos do sistema

- **Python 3.10 ou superior**
  - Windows: https://www.python.org/downloads/
  - Linux/Ubuntu: `sudo apt install python3 python3-venv python3-pip`
- Acesso a internet (para a macro consultar a API da Aguas Andinas)
- Acesso ao banco MySQL na AWS RDS (credenciais ja incluidas em `config.py`)

---

## 1. Configuracao inicial (uma unica vez)

### Windows

```bat
setup.bat
```

### Linux / Ubuntu

```bash
chmod +x setup.sh
./setup.sh
```

Isso cria a pasta `venv/` com todas as dependencias instaladas.

> Se preferir fazer manualmente no Linux:
> ```bash
> python3 -m venv venv
> source venv/bin/activate
> pip install -r requirements.txt
> ```

---

## 2. Rodar a Macro

A macro consulta a API da Aguas Andinas para cada RUT pendente no banco
e salva telefone/email validados.

```bat
venv\Scripts\activate
python macro\valida_dados_aguasandinas_v2.1\executar_db.py
```

### Opcoes avancadas

| Parametro | Descricao | Default |
|-----------|-----------|---------|
| `--lotes N` | Processa no maximo N lotes | sem limite |
| `--tamanho N` | Registros por lote | 500 |
| `--pausa N` | Pausa (segundos) entre requisicoes | 1.0 |
| `--dry-run` | Consulta a API mas NAO salva no banco | desativado |

Exemplos:
```bat
:: Processa 10 lotes de 100 registros com pausa de 2s
python macro\valida_dados_aguasandinas_v2.1\executar_db.py --lotes 10 --tamanho 100 --pausa 2

:: Teste sem gravar no banco
python macro\valida_dados_aguasandinas_v2.1\executar_db.py --dry-run --lotes 1
```

### Comportamento esperado

- A macro retoma automaticamente do ponto onde parou (query por `status = 'pendente'`)
- Se houver falha na API, o registro permanece como `pendente` e sera retentado na proxima execucao
- A macro para sozinha quando nao ha mais registros pendentes

---

## 3. Rodar o Dashboard

O dashboard Dash fica disponivel em `http://127.0.0.1:8050`.

```bat
venv\Scripts\activate
cd dashboard_macros
python run_dashboard.py
```

Ou a partir da raiz:
```bat
venv\Scripts\activate
python -m dashboard_macros
```

### Acesso

| Campo | Valor |
|-------|-------|
| URL | http://127.0.0.1:8052 |
| Usuario | `aguasandinas` |
| Senha | `dashboard2026` |

### Refresh automatico

O dashboard atualiza os dados automaticamente **duas vezes por dia**:
- **08h00** — refresh matinal
- **17h00** — refresh vespertino

Para iniciar e deixar rodando em background (fecha o terminal mas mantem o processo):
```bat
start /B venv\Scripts\python.exe dashboard_macros\run_dashboard.py > dashboard.log 2>&1
```

---

## 4. Credenciais do banco de dados

Definidas em `config.py` na raiz do projeto.

| Parametro | Valor |
|-----------|-------|
| Host | `integracoes-assisty.ccr0wsmgsayo.us-east-1.rds.amazonaws.com` |
| Porta | `3306` |
| Usuario | `time_dados` |
| Senha | `Assisty@2025!` |
| Banco (macro/dashboard AA) | `bd_Automacoes_time_dados_aguas_andinas` |
| Banco (dashboard CPFL) | `bd_Automacoes_time_dados_cpfl` |

Para alterar as credenciais, edite diretamente o arquivo `config.py`.

---

## 5. Estrutura de arquivos essenciais

```
projeto_orquestracao_aguas_andinas/
├── config.py                                  # credenciais do banco
├── requirements.txt                           # dependencias Python
├── setup.bat                                  # setup do venv (Windows)
├── INSTRUCOES.md                              # este arquivo
│
├── macro/
│   └── valida_dados_aguasandinas_v2.1/
│       ├── executar_db.py                     # ENTRY POINT da macro
│       ├── config.py                          # helper de paths
│       └── core/
│           └── extrator.py                    # cliente HTTP da API AA
│
├── etl/
│   └── transformation/
│       └── macro_aa/
│           ├── __init__.py
│           └── interpretar_resposta_aa.py     # logica de interpretacao
│
└── dashboard_macros/
    ├── run_dashboard.py                       # ENTRY POINT do dashboard
    ├── dashboard.py                           # layout e callbacks Dash
    ├── refresh_scheduler.py                   # agendamento 08h/17h
    ├── __init__.py
    ├── __main__.py
    ├── data/
    │   └── loader.py                          # queries SQL
    ├── processing/
    │   └── processing.py                      # transformacoes de dados
    └── service/
        └── orchestrator.py                    # orquestracao do refresh
```

---

## 6. Solucao de problemas

**`ModuleNotFoundError`**: certifique-se de que o venv esta ativado (`venv\Scripts\activate`)
e que voce esta executando a partir da **raiz** do projeto (nao de dentro de subpastas).

**Macro trava ou cai com exit code 1**: e normal por timeouts da API. Reinicie — ela retoma automaticamente dos registros pendentes.

**Dashboard nao abre**: verifique se a porta 8050 nao esta em uso:
```bat
netstat -ano | findstr :8050
```

**Erro de conexao com o banco**: confirme acesso a internet e que o IP local tem permissao no security group da RDS.

**Linux — porta 8050 ja em uso**:
```bash
lsof -i :8050
kill -9 <PID>
```

**Linux — macro em background com log**:
```bash
source venv/bin/activate
nohup python macro/valida_dados_aguasandinas_v2.1/executar_db.py > macro.log 2>&1 &
tail -f macro.log   # acompanhar em tempo real
```
