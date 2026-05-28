import tkinter as tk
from tkinter import ttk
from datetime import datetime

class WidgetLog(ttk.Frame):
    """Widget para exibir informações de log."""
    def __init__(self, parent):
        super().__init__(parent)

        self.expandido = False
        self._build()

    def _build(self):
        topo = ttk.Frame(self)
        topo.pack(anchor="w")

        self.btn_toggle = ttk.Button(topo, text="▶ Mostrar Logs", command=self.toggle)
        self.btn_toggle.pack(side="left", padx=5)

        self.btn_limpar = ttk.Button(topo, text="Limpar", command=self.limpar)
        # self.btn_limpar.pack(side="left", padx=5)
        # self.btn_limpar.pack_forget()

        self.texto = tk.Text(self, height=8, state="disabled", font=("Consolas", 9))
        self.texto.tag_config("INFO", foreground="black")
        self.texto.tag_config("SUCESSO", foreground="green")
        self.texto.tag_config("AVISO", foreground="orange")
        self.texto.tag_config("ERRO", foreground="red")

    def toggle(self):

        self.expandido = not self.expandido

        if self.expandido:
            self.btn_toggle.config(text="▼ Ocultar Logs")
            self.texto.pack(fill="both", expand=True)
            self.btn_limpar.pack(side="left", padx=5)
        else:
            self.btn_toggle.config(text="▶ Mostrar Logs")
            self.texto.pack_forget()
            self.btn_limpar.pack_forget()

    def adicionar(self, msg, nivel="INFO"):

        agora = datetime.now().strftime("%H:%M:%S")

        self.texto.config(state="normal")
        self.texto.insert("end", f"[{agora}] [{nivel}] {msg}\n", nivel)
        self.texto.config(state="disabled")
        self.texto.see("end")

    def limpar(self):
        self.texto.config(state="normal")
        self.texto.delete("1.0", "end")
        self.texto.config(state="disabled")
    