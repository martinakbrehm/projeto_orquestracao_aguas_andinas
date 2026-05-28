import tkinter as tk
from tkinter import ttk

class ProgressoInfoWidget(ttk.Frame):
    """Widget para exibir informações de progresso."""
    def __init__(self, parent):
        super().__init__(parent)

        self.var_linha = tk.StringVar(value="Linha atual: --")
        self.var_total = tk.StringVar(value="Total: --")
        self.var_percentual = tk.StringVar(value="Progresso: 0%")

        self._build()

    def _build(self):
        ttk.Label(self, textvariable=self.var_linha).pack(anchor="w")
        ttk.Label(self, textvariable=self.var_total).pack(anchor="w")
        ttk.Label(self, textvariable=self.var_percentual, foreground="#0066CC").pack(anchor="w")

    def atualizar(self, linha=None, total=None, percentual=None):
        if linha is not None:
            self.var_linha.set(f"Linha atual: {linha}")
        if total is not None:
            self.var_total.set(f"Total: {total}")
        if percentual is not None:
            self.var_percentual.set(f"Progresso: {percentual:.2f}%")

        self.update_idletasks()
    
    def resetar(self):
        self.var_linha.set("Linha atual: --")
        self.var_total.set("Total: --")
        self.var_percentual.set("Progresso: 0%")