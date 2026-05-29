import sys
import os
import threading
import pandas as pd
sys.path.insert(0, os.path.dirname(__file__))

import dash
from dash import dcc, html, dash_table
from flask import jsonify, request
import dash_auth

try:
    from .data import loader
    from .service import orchestrator
    from .refresh_scheduler import executar_refresh
except ImportError:
    from data import loader
    from service import orchestrator
    from refresh_scheduler import executar_refresh

REFRESH_INTERVAL_MS = 12 * 60 * 60 * 1000  # 12 horas em milissegundos

COLUMN_LABELS = {
    "dia":        "Data",
    "total":      "Total",
    "ativos":     "Ativos",
    "pct_ativos": "% Ativos",
    "inativos":   "Inativos",
    "pct_inativos": "% Inativos",
}

COLUMN_LABELS_AA = {
    "dia":          "Data",
    "total":        "Total",
    "ativos":       "Com telefone",
    "pct_ativos":   "% Com telefone",
    "inativos":     "Sem telefone",
    "pct_inativos": "% Sem telefone",
}

external_stylesheets = [
    "https://fonts.googleapis.com/css?family=Roboto:400,700&display=swap",
    "https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css",
]
app = dash.Dash(__name__, external_stylesheets=external_stylesheets)
app.title = "Dashboard Aguas Andinas"

# Autenticação básica para todo o app
auth = dash_auth.BasicAuth(
    app,
    {'aguasandinas': 'dashboard2026'}
)

TITLE_STYLE         = {"fontFamily": "Roboto", "color": "#1a237e", "fontWeight": "700", "fontSize": "22px"}
SECTION_TITLE_STYLE = {"fontFamily": "Roboto", "color": "#3949ab", "fontWeight": "700", "fontSize": "18px"}
SUBTITLE_STYLE      = {"fontFamily": "Roboto", "color": "#283593", "fontWeight": "700", "fontSize": "16px"}

_df_inicial             = pd.DataFrame()
_opcoes_dia_inicial     = []
_opcoes_empresa_inicial = []
_opcoes_arquivo_inicial = []

# Refresh inicial das tabelas materializadas (em background para não bloquear startup)
# Horários agendados para refresh automático (hora cheia)
_REFRESH_HORARIOS = {8, 17}  # refresh automático: 08h e 17h


def _executar_refresh_once():
    """Executa um único ciclo de refresh (usado pelo callback do interval e pelo scheduler)."""
    try:
        executar_refresh()
    except Exception as e:
        print(f"[WARN] Refresh falhou: {e}")
    finally:
        loader.invalidar_cache()
        print("[INFO] Cache invalidado após refresh")
    # Pré-aquece o cache com dados frescos do banco (independente de browser aberto)
    try:
        loader.carregar_dados("aguas_andinas")
        print("[INFO] Cache pré-aquecido com dados atualizados")
    except Exception as e:
        print(f"[WARN] Falha ao pré-aquecer cache: {e}")


def _refresh_bg():
    """Scheduler de refresh: roda às 8h, 12h e 17h. Verifica a cada minuto."""
    import time as _time
    from datetime import datetime
    _ja_rodou = set()  # evita rodar mais de uma vez no mesmo horário
    while True:
        agora = datetime.now()
        chave = (agora.date(), agora.hour)
        if agora.hour in _REFRESH_HORARIOS and chave not in _ja_rodou:
            print(f"[INFO] Refresh agendado das {agora.hour}h iniciando...")
            _ja_rodou.add(chave)
            _executar_refresh_once()
        # Limpa chaves de dias anteriores para não crescer indefinidamente
        hoje = agora.date()
        _ja_rodou = {c for c in _ja_rodou if c[0] == hoje}
        _time.sleep(60)  # verifica a cada minuto


threading.Thread(target=_refresh_bg, daemon=True).start()


@app.server.before_request
def _log_incoming_requests():
    try:
        _ = request.path
    except Exception:
        pass


app.layout = html.Div([

    # Cabecalho
    html.Div([
        html.Img(src="https://img.icons8.com/color/48/000000/combo-chart--v2.png",
                 style={"height": "48px", "marginRight": "16px"}),
        html.H1("Dashboard de Macros - Aguas Andinas",
                style={**TITLE_STYLE, "display": "inline-block", "verticalAlign": "middle", "margin": 0}),
    ], style={"display": "flex", "alignItems": "center", "marginBottom": "16px", "marginTop": "16px"}),

    # Auto-refresh a cada 20 minutos (compartilhado pelas abas)
    dcc.Interval(id="interval-refresh", interval=REFRESH_INTERVAL_MS, n_intervals=0),

    # Abas
    html.Div([

            # Info bar
            html.Div(id="info-registros-aa",
                     style={"marginBottom": "12px", "fontSize": "14px", "fontWeight": "600",
                            "marginTop": "12px"}),

            # Filtros
            html.Div([
                html.Div([
                    html.Label("Filtrar mês", style={"fontWeight": "700", "fontSize": "13px",
                                                      "marginBottom": "6px", "display": "block",
                                                      "color": "#1a237e"}),
                    dcc.Dropdown(
                        id="filtro-mes-dropdown-aa",
                        options=[],
                        multi=True, clearable=True, placeholder="Todos os meses",
                        style={"width": "100%"},
                    ),
                ], style={"flex": "0.7", "minWidth": "180px", "background": "#fff", "padding": "10px",
                          "borderRadius": "8px", "boxShadow": "0 1px 6px rgba(44,62,80,0.06)"}),

                html.Div([
                    html.Label("Filtrar dia", style={"fontWeight": "700", "fontSize": "13px",
                                                      "marginBottom": "6px", "display": "block",
                                                      "color": "#1a237e"}),
                    dcc.Dropdown(
                        id="resumo-dia-dropdown-aa",
                        options=[],
                        multi=True, clearable=True, placeholder="Todos os dias",
                        style={"width": "100%"},
                    ),
                ], style={"flex": "0.7", "minWidth": "180px", "background": "#fff", "padding": "10px",
                          "borderRadius": "8px", "boxShadow": "0 1px 6px rgba(44,62,80,0.06)"}),

            ], style={"display": "flex", "gap": "12px", "alignItems": "stretch",
                      "marginBottom": "12px", "marginTop": "8px"}),

            # Conteudo principal Aguas Andinas
            dcc.Loading(type="circle", children=html.Div([

                # Card: Resumo diario AA
                html.Div([
                    html.H2("Resumo por data de processamento",
                            style={**SECTION_TITLE_STYLE, "marginBottom": "6px"}),
                    html.P(
                        "Total = consultas executadas no dia. "
                        "Com Telefone = RUT com telefone encontrado. "
                        "Sem Telefone = RUT sem telefone no retorno.",
                        style={"fontSize": "13px", "color": "#555", "marginBottom": "10px",
                               "background": "#e8f5e9", "padding": "8px 14px", "borderRadius": "6px",
                               "borderLeft": "4px solid #2e7d32"},
                    ),
                    dash_table.DataTable(
                        id="tabela-resumo-aa",
                        columns=[{"name": COLUMN_LABELS_AA.get(c, c), "id": c}
                                  for c in ["dia", "total", "ativos", "pct_ativos", "inativos", "pct_inativos"]],
                        data=[],
                        style_table={"overflowX": "auto"},
                        style_cell={"textAlign": "center", "fontFamily": "Roboto", "fontSize": "15px",
                                    "padding": "10px", "whiteSpace": "normal", "height": "auto"},
                        style_header={"backgroundColor": "#1565c0", "color": "white",
                                       "fontWeight": "bold", "fontFamily": "Roboto", "fontSize": "15px"},
                        style_data_conditional=[
                            {"if": {"row_index": "odd"}, "backgroundColor": "#e3f2fd"},
                            {"if": {"filter_query": '{dia} = "Total"'}, "fontWeight": "bold",
                             "backgroundColor": "#bbdefb"},
                        ],
                        page_size=20,
                    ),
                ], style={"background": "#fff", "borderRadius": "8px", "boxShadow": "0 2px 8px #e0e0e0",
                          "padding": "16px", "marginBottom": "18px"}),

                # Card: Distribuicao de status AA
                html.Div([
                    html.H3("Distribuicao por status",
                            style={**SUBTITLE_STYLE, "marginTop": "0", "marginBottom": "6px"}),
                    html.P(
                        "Contagem total de RUTs por status na fila. "
                        "Inclui todos os estados: pendente, processando, com e sem telefone.",
                        style={"fontSize": "13px", "color": "#555", "marginBottom": "10px",
                               "background": "#fff3e0", "padding": "8px 14px", "borderRadius": "6px",
                               "borderLeft": "4px solid #e65100"},
                    ),
                    dash_table.DataTable(
                        id="tabela-status-aa",
                        columns=[{"name": "Status", "id": "mensagem"},
                                  {"name": "Quantidade", "id": "quantidade"}],
                        data=[],
                        style_table={"overflowX": "auto", "borderRadius": "8px",
                                     "boxShadow": "0 2px 8px #e0e0e0", "marginTop": "12px"},
                        style_cell={"textAlign": "left", "fontFamily": "Roboto", "fontSize": "14px",
                                    "padding": "8px", "whiteSpace": "normal", "height": "auto"},
                        style_cell_conditional=[
                            {"if": {"column_id": "mensagem"},  "width": "70%"},
                            {"if": {"column_id": "quantidade"}, "width": "30%", "textAlign": "right"},
                        ],
                        style_header={"backgroundColor": "#1565c0", "color": "white",
                                       "fontWeight": "bold", "fontFamily": "Roboto", "fontSize": "15px"},
                        style_data_conditional=[
                            {"if": {"row_index": "odd"}, "backgroundColor": "#e3f2fd"},
                        ],
                        page_size=10,
                    ),
                ], style={"background": "#fff", "borderRadius": "8px", "boxShadow": "0 2px 8px #e0e0e0",
                          "padding": "12px", "marginBottom": "22px"}),

                # Card: Distribuicao por resposta AA
                html.Div([
                    html.H3("Distribuição por resposta",
                            style={**SUBTITLE_STYLE, "marginTop": "0", "marginBottom": "6px"}),
                    html.P(
                        "Quantidade de RUTs por tipo de retorno da macro, no período selecionado.",
                        style={"fontSize": "13px", "color": "#555", "marginBottom": "10px",
                               "background": "#e3f2fd", "padding": "8px 14px", "borderRadius": "6px",
                               "borderLeft": "4px solid #1565c0"},
                    ),
                    dash_table.DataTable(
                        id="tabela-respostas-aa",
                        columns=[
                            {"name": "Resposta",    "id": "mensagem"},
                            {"name": "Quantidade",  "id": "quantidade"},
                        ],
                        data=[],
                        style_table={"overflowX": "auto", "borderRadius": "8px",
                                     "boxShadow": "0 2px 8px #e0e0e0", "marginTop": "12px"},
                        style_cell={"textAlign": "left", "fontFamily": "Roboto", "fontSize": "14px",
                                    "padding": "8px", "whiteSpace": "normal", "height": "auto"},
                        style_cell_conditional=[
                            {"if": {"column_id": "mensagem"},  "width": "70%"},
                            {"if": {"column_id": "quantidade"}, "width": "30%", "textAlign": "right"},
                        ],
                        style_header={"backgroundColor": "#1565c0", "color": "white",
                                       "fontWeight": "bold", "fontFamily": "Roboto", "fontSize": "15px"},
                        style_data_conditional=[
                            {"if": {"row_index": "odd"}, "backgroundColor": "#e3f2fd"},
                        ],
                        page_size=12,
                    ),
                ], style={"background": "#fff", "borderRadius": "8px", "boxShadow": "0 2px 8px #e0e0e0",
                          "padding": "12px", "marginBottom": "22px"}),

                # Card: Resultados por arquivo de staging AA
                html.Div([
                    html.H3("Resultados por arquivo de staging",
                            style={**SUBTITLE_STYLE, "marginTop": "0", "marginBottom": "6px"}),
                    html.P(
                        "Cada linha = um arquivo importado. "
                        "Clientes únicos = RUTs distintos naquele staging. "
                        "Processados = já passaram pela macro.",
                        style={"fontSize": "13px", "color": "#555", "marginBottom": "10px",
                               "background": "#e8f5e9", "padding": "8px 14px", "borderRadius": "6px",
                               "borderLeft": "4px solid #2e7d32"},
                    ),
                    dash_table.DataTable(
                        id="tabela-staging-aa",
                        columns=[
                            {"name": "Arquivo",            "id": "arquivo"},
                            {"name": "Data carga",          "id": "data_carga"},
                            {"name": "RUTs no banco",       "id": "clientes_no_banco"},
                            {"name": "Processados",         "id": "processados"},
                            {"name": "Pendentes",           "id": "pendentes"},
                            {"name": "Com telefone",        "id": "com_telefone"},
                            {"name": "Sem telefone",        "id": "sem_telefone"},
                        ],
                        data=[],
                        style_table={"overflowX": "auto", "borderRadius": "8px",
                                     "boxShadow": "0 2px 8px #e0e0e0", "marginTop": "4px"},
                        style_cell={"textAlign": "center", "fontFamily": "Roboto", "fontSize": "13px",
                                    "padding": "7px 5px", "whiteSpace": "normal", "height": "auto",
                                    "minWidth": "60px"},
                        style_cell_conditional=[
                            {"if": {"column_id": "arquivo"},
                             "textAlign": "left", "minWidth": "180px", "maxWidth": "260px"},
                        ],
                        style_header={"backgroundColor": "#1565c0", "color": "white",
                                       "fontWeight": "bold", "fontFamily": "Roboto", "fontSize": "13px",
                                       "padding": "8px 5px", "whiteSpace": "normal"},
                        style_data_conditional=[
                            {"if": {"row_index": "odd"}, "backgroundColor": "#e3f2fd"},
                        ],
                        page_size=10,
                    ),
                ], style={"background": "#fff", "borderRadius": "8px", "boxShadow": "0 2px 8px #e0e0e0",
                          "padding": "16px", "marginBottom": "18px"}),

            ], style={"background": "#dde9f8", "padding": "28px", "borderRadius": "10px",
                      "marginBottom": "18px"})),

    ]),  # fim Conteudo Aguas Andinas

    html.Div(style={"height": "8px"}),

], style={"maxWidth": "1100px", "margin": "0 auto", "fontFamily": "Roboto",
          "background": "#f0f2f8", "padding": "16px 0"})


# --------------------------------------------------------------------------
# Callbacks — Aguas Andinas
# --------------------------------------------------------------------------

@app.callback(
    [
        dash.dependencies.Output("filtro-mes-dropdown-aa", "options"),
        dash.dependencies.Output("filtro-mes-dropdown-aa", "value"),
        dash.dependencies.Output("resumo-dia-dropdown-aa", "options"),
        dash.dependencies.Output("resumo-dia-dropdown-aa", "value"),
        dash.dependencies.Output("info-registros-aa",      "children"),
    ],
    [
        dash.dependencies.Input("interval-refresh", "n_intervals"),
    ]
)
def atualizar_opcoes_filtros_aa(n_intervals):
    ctx = dash.callback_context
    if ctx.triggered and ctx.triggered[0]["prop_id"] == "interval-refresh.n_intervals" and n_intervals > 0:
        threading.Thread(target=_executar_refresh_once, daemon=True).start()
    df = loader.carregar_dados("aguas_andinas")
    if df.empty:
        loader.invalidar_cache("aguas_andinas")
        df = loader.carregar_dados("aguas_andinas")
    if df.empty:
        return [], None, [], None, "Sem dados para Aguas Andinas (aguardando refresh...)"

    opcoes_dia = sorted(df["dia"].dropna().unique())

    meses_vistos = {}
    for d in opcoes_dia:
        ds = str(d)
        if len(ds) >= 7:
            chave_mes = ds[:7]
            if chave_mes not in meses_vistos:
                try:
                    mes_num = int(chave_mes[5:7])
                    ano = chave_mes[:4]
                    meses_vistos[chave_mes] = f"{mes_num:02d}/{ano}"
                except ValueError:
                    pass
    opcoes_dropdown_mes = [{"label": meses_vistos[k], "value": k} for k in sorted(meses_vistos.keys())]

    total_processados = int(df["qtd"].sum()) if "qtd" in df.columns else len(df)
    info = f"Processados: {total_processados:,}  |  Dias: {len(opcoes_dia)}"
    return (
        opcoes_dropdown_mes,
        None,
        [{"label": str(d), "value": str(d)} for d in opcoes_dia],
        None,
        info,
    )


@app.callback(
    [
        dash.dependencies.Output("tabela-resumo-aa",    "data"),
        dash.dependencies.Output("tabela-status-aa",    "data"),
        dash.dependencies.Output("tabela-respostas-aa", "data"),
        dash.dependencies.Output("tabela-staging-aa",   "data"),
    ],
    [
        dash.dependencies.Input("filtro-mes-dropdown-aa", "value"),
        dash.dependencies.Input("resumo-dia-dropdown-aa", "value"),
    ]
)
def atualizar_dashboard_aa(filtro_mes, resumo_sel):
    filtro_datas_combinado = []
    if filtro_mes:
        for m in (filtro_mes if isinstance(filtro_mes, list) else [filtro_mes]):
            filtro_datas_combinado.append(f"mes:{m}")
    if resumo_sel:
        for d in (resumo_sel if isinstance(resumo_sel, list) else [resumo_sel]):
            filtro_datas_combinado.append(str(d))
    try:
        data_resumo, data_status, _ = orchestrator.build_dashboard_data(
            filtro_datas_combinado if filtro_datas_combinado else None,
            None,
            tipo_macro="aguas_andinas",
            granularidade="combo",
        )
    except Exception as _e:
        import traceback
        print(f"[ERRO atualizar_dashboard_aa] {_e}")
        traceback.print_exc()
        data_resumo = []
        data_status = []

    # Distribuicao por resposta (mensagem da macro), filtrada por data
    data_respostas = []
    try:
        df_raw = loader.carregar_dados("aguas_andinas")
        if not df_raw.empty and "mensagem" in df_raw.columns:
            dff = df_raw.copy()
            if filtro_mes or resumo_sel:
                dias_exp = []
                if filtro_mes:
                    for m in (filtro_mes if isinstance(filtro_mes, list) else [filtro_mes]):
                        dias_exp.extend(
                            str(d) for d in dff["dia"].dropna().unique()
                            if str(d).startswith(m)
                        )
                if resumo_sel:
                    for d in (resumo_sel if isinstance(resumo_sel, list) else [resumo_sel]):
                        dias_exp.append(str(d))
                if dias_exp:
                    dff = dff[dff["dia"].astype(str).isin(dias_exp)]
            data_respostas = (
                dff[dff["mensagem"].notna()]
                .groupby("mensagem")["qtd"].sum()
                .reset_index()
                .rename(columns={"qtd": "quantidade"})
                .sort_values("quantidade", ascending=False)
                .to_dict("records")
            )
    except Exception as _e:
        print(f"[WARN respostas] {_e}")

    _STATUS_LABELS = {
        "pendente":              "Pendente",
        "processando":           "Processando",
        "telefone_validado":     "Telefone validado",
        "telefone_nao_validado": "Telefone não validado",
    }
    data_status = [
        {**row, "mensagem": _STATUS_LABELS.get(row.get("mensagem", ""), row.get("mensagem", ""))}
        for row in data_status
    ]

    return data_resumo, data_status, data_respostas, loader.carregar_staging_aa().to_dict("records")





@app.server.route("/_debug/data")
def debug_data():
    try:
        print("DEBUG: Chamando build_dashboard_data")
        import traceback
        data_resumo, data_status, _ = orchestrator.build_dashboard_data(
            [], None, "aguas_andinas", None, None
        )
        print(f"DEBUG: Retornou {len(data_resumo)} registros no resumo")
        return jsonify({
            "data_resumo":  data_resumo,
            "data_status":  data_status,
        })
    except Exception as e:
        print(f"DEBUG: Erro: {e}")
        print(f"DEBUG: Traceback: {traceback.format_exc()}")
        return jsonify({"error": str(e), "traceback": traceback.format_exc()})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8050, debug=False, use_reloader=False)
