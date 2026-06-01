#!/usr/bin/env python3
"""
Launcher para o Dashboard de Macros Neo
Executa o dashboard com autenticação básica
"""

import sys
import os

# Adiciona o diretório raiz ao path
root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, root_dir)

# Adiciona o diretório do dashboard ao path
dashboard_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, dashboard_dir)

# Agora importa e executa
from dashboard import app

if __name__ == '__main__':
    print("Iniciando Dashboard CPFL...")
    print("Autenticacao: usuario 'cpfl', senha 'dashboard2026'")
    print("URL: http://127.0.0.1:8052")
    app.run(host='0.0.0.0', port=8052, debug=False, use_reloader=False)