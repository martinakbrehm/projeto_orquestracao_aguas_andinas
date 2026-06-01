#!/bin/bash
# =============================================================================
# setup.sh — Cria o ambiente virtual e instala todas as dependencias (Linux/macOS)
# Execute UMA VEZ antes de rodar a macro ou o dashboard.
# Requisito: Python 3.10 ou superior instalado.
#   Ubuntu/Debian: sudo apt install python3 python3-venv python3-pip
# =============================================================================

set -e

echo ""
echo "====================================================="
echo " Setup - Projeto Orquestracao Aguas Andinas"
echo "====================================================="
echo ""

# Verifica Python 3.10+
PYTHON=$(command -v python3 || command -v python || true)
if [ -z "$PYTHON" ]; then
    echo "[ERRO] Python nao encontrado. Instale com:"
    echo "       sudo apt install python3 python3-venv python3-pip"
    exit 1
fi

PY_VER=$($PYTHON --version 2>&1)
echo "Python encontrado: $PY_VER"

# Cria venv
if [ -d "venv" ]; then
    echo "[OK] venv ja existe, pulando criacao."
else
    echo "Criando ambiente virtual em ./venv ..."
    $PYTHON -m venv venv
    echo "[OK] venv criado."
fi

# Ativa venv e instala dependencias
echo ""
echo "Instalando dependencias (requirements.txt)..."
source venv/bin/activate
pip install --upgrade pip --quiet
pip install -r requirements.txt

echo ""
echo "====================================================="
echo " Setup concluido com sucesso!"
echo ""
echo " Para rodar a MACRO:"
echo "   source venv/bin/activate"
echo "   python macro/valida_dados_aguasandinas_v2.1/executar_db.py"
echo ""
echo " Para rodar o DASHBOARD:"
echo "   source venv/bin/activate"
echo "   cd dashboard_macros"
echo "   python run_dashboard.py"
echo "====================================================="
echo ""
