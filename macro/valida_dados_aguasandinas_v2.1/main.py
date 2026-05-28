import tkinter as tk
from interface.interface import InterfacePrincipal
from config import BASE_DIR
from core.validador import Validador


if __name__ == "__main__":
    
    root = tk.Tk()
    app = InterfacePrincipal(root)
    root.mainloop()

    #caminho planilha = planilha/Base de Datos 1_Chile_Renta - Patente (2).xlsx

    # caminho_planilha = BASE_DIR / "planilha" / "Base de Datos 1_Chile_Renta - Patente (2).csv"
    # caminho_planilha = str(caminho_planilha)

    # # Instancia o validador
    # validador = Validador(caminho_csv=caminho_planilha)
    # validador.processamento()
    # validador.processar_linhas_faltantes()