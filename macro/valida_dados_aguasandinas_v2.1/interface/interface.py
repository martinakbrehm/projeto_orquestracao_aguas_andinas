import os
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import threading
import queue

from core.gerenciador_dados import GerenciadorDados
from core.validador import Validador
from .widgets.progresso_info import ProgressoInfoWidget
from .widgets.widget_log import WidgetLog

class InterfacePrincipal:
    def __init__(self, root):
        self.root = root
        self.root.title("Validados - Águas Andinas")
        self.root.geometry("720x550")

        self.queue = queue.Queue()

        self.caminho_csv = None
        self.validador = None
        self.thread = None

        self._build_layout()
        self._loop_fila()

    # =========================
    # LAYOUT
    # =========================
    def _build_layout(self):

        # Seção arquivo
        main = ttk.Frame(self.root, padding=15)
        main.pack(fill="both", expand=True)

        frame_arquivo = ttk.LabelFrame(main, text="Projeto", padding=10)
        frame_arquivo.pack(fill="x", pady=5)

        self.lbl_arquivo = ttk.Label(frame_arquivo, text="Nenhuma planilha selecionada")
        self.lbl_arquivo.pack(side="left", padx=5)

        self.btn_selecionar = ttk.Button(
            frame_arquivo,
            text="Selecionar Planilha",
            command=self._selecionar_planilha
        )
        self.btn_selecionar.pack(side="right")

        # Status Geral
        self.lbl_status = ttk.Label(main, text="Status: -- / --")
        self.lbl_status.pack(anchor="w", pady=5)

        # Botões de controle
        frame_botoes = ttk.Frame(main)
        frame_botoes.pack(fill="x", pady=5)

        self.btn_iniciar = ttk.Button(frame_botoes, text="Iniciar", command=self._iniciar)
        self.btn_iniciar.pack(side="left", padx=5)

        self.btn_pausar = ttk.Button(frame_botoes, text="Pausar", command=self._pausar)
        self.btn_pausar.pack(side="left", padx=5)
        self.btn_pausar.config(state="disabled")

        self.btn_parar = ttk.Button(frame_botoes, text="Encerrar", command=self._parar)
        self.btn_parar.pack(side="left", padx=5)
        self.btn_parar.config(state="disabled")

        # Barra de progresso
        self.progress = ttk.Progressbar(main, length=600)
        self.progress.pack(pady=5)

        # Widget ProgressoInfo
        self.widget_progresso = ProgressoInfoWidget(main)
        self.widget_progresso.pack(fill="x", pady=5)

        # Widget Log
        self.widget_log = WidgetLog(main)
        self.widget_log.pack(fill="both", expand=True, pady=5)

    # =========================
    # THREAD (LOOP)
    # ========================+
    def _iniciar(self):
        if not self.caminho_csv:
            messagebox.showwarning("Aviso", "Selecione uma planilha primeiro.")
            return

        self._resetar_estado_execucao(limpar_status=False)
        self.btn_selecionar.config(state="disabled")

        self.validador = Validador(
            self.caminho_csv,
            callback_progresso=self._callback_progresso,
        )

        self.thread = threading.Thread(
            target=self.validador.processamento,
            daemon=True
        )
        self.thread.start()

        self.btn_iniciar.config(state="disabled")
        self.btn_pausar.config(state="normal")
        self.btn_parar.config(state="normal")

    def _pausar(self):
        self.validador.pausado = not self.validador.pausado

        if self.validador.pausado:
            self.btn_pausar.config(text="Retomar")
            self.widget_log.adicionar("Processo pausado", "AVISO")
        else:
            self.btn_pausar.config(text="Pausar")
            self.widget_log.adicionar("Processo retomado", "INFO")

    def _parar(self):
        resposta = messagebox.askyesnocancel(
        "Encerrar", "Sim = Encerrar e ver resultados\nNão = Apenas encerrar"
        )

        if resposta is None:
            return
        
        self.btn_pausar.config(state="disabled")
        self.btn_parar.config(state="disabled")
        
        if self.validador is not None:
            self.validador.rodando = False

        if resposta:  # Sim
            caminho_final = self.validador.dados.caminho_resultado
            os.startfile(os.path.dirname(caminho_final)) # Abre a pasta
        
    
    def _selecionar_planilha(self):
        caminho = filedialog.askopenfilename(
        filetypes=[("CSV", "*.csv")]
        )

        if not caminho:
            return

        self.caminho_csv = caminho
        self.lbl_arquivo.config(text=os.path.basename(caminho))
        self._resetar_estado_execucao()

        ger = GerenciadorDados(caminho)

        processadas, total = ger.obter_status()

        if processadas > 0:
            resposta = messagebox.askyesno(
                "Progresso encontrado",
                f"Encontrado progresso: {processadas}/{total}\nDeseja continuar?"
            )   

            if not resposta:
                ger.inicializar_arquivo_resultado(continuar=False)
                processadas = 0

        self.lbl_status.config(text=f"Status: {processadas} / {total}")
        self.progress["value"] = (processadas / total * 100) if total > 0 else 0
        self.widget_progresso.atualizar(
            linha=processadas if total > 0 else None,
            total=total if total > 0 else None,
            percentual=(processadas / total * 100) if total > 0 else 0
        )
        self.widget_log.adicionar(f"Planilha selecionada: {os.path.basename(caminho)}", "INFO")
        if processadas > 0:
            self.widget_log.adicionar(f"Progresso encontrado: {processadas}/{total}", "AVISO")

    # ===========================
    # CALLBACKS
    # ===========================
    def _callback_progresso(self, dados):
        self.queue.put(("progresso", dados))

    def _resetar_estado_execucao(self, limpar_status=True):
        self.widget_log.limpar()
        self.widget_progresso.resetar()
        self.progress["value"] = 0
        if limpar_status:
            self.lbl_status.config(text="Status: -- / --")
        self.btn_iniciar.config(state="normal")
        self.btn_pausar.config(state="disabled", text="Pausar")
        self.btn_parar.config(state="disabled")
        self.btn_selecionar.config(state="normal")

    def _finalizar_execucao(self):
        self.btn_iniciar.config(state="normal")
        self.btn_pausar.config(state="disabled", text="Pausar")
        self.btn_parar.config(state="disabled")
        self.btn_selecionar.config(state="normal")


    def _loop_fila(self):

        try:
            while True:
                tipo, dados = self.queue.get_nowait() # get_nowait() retorna None se a fila estiver vazia

                if tipo == "progresso":
                    self._atualizar_progresso(dados)

        except queue.Empty:
            pass

        self.root.after(100, self._loop_fila)

    def _atualizar_progresso(self, dados):
        status = dados.get("status")

        if status == "iniciado":
            self.widget_log.adicionar(dados.get("mensagem", "Processo iniciado"), "INFO")

        elif status == "processando":
            valor = dados["progresso"]
            self.progress["value"] = max(0, min(100, valor))

            self.widget_progresso.atualizar(
                linha=dados["linha_atual"],
                total=dados["total_linhas"],
                percentual=dados["progresso"]
            )

            # self.widget_log.adicionar(
            #     dados.get(
            #         "mensagem",
            #         f"Processando linha {dados['linha_atual']} de {dados['total_linhas']} ({dados['progresso']:.2f}%)"
            #     ),
            #     "INFO"
            # )

        elif status == "erro_linha":
            self.widget_log.adicionar(dados.get("mensagem", "Erro ao processar linha"), "ERRO")

        elif status == "erro":
            self.widget_log.adicionar(dados.get("mensagem", "Erro inesperado no processo"), "ERRO")
            self._finalizar_execucao()

        elif status == "interrompido":
            self.widget_log.adicionar(dados.get("mensagem", "Processo encerrado"), "AVISO")
            self._finalizar_execucao()

        elif status == "concluido":
            self.widget_log.adicionar(dados.get("mensagem", "Processo finalizado com sucesso"), "SUCESSO")
            self._finalizar_execucao()
