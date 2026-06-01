@echo off
:: =============================================================================
:: setup.bat — Cria o ambiente virtual e instala todas as dependencias
:: Execute UMA VEZ antes de rodar a macro ou o dashboard.
:: Requisito: Python 3.10 ou superior instalado e disponivel no PATH.
:: =============================================================================

echo.
echo =====================================================
echo  Setup - Projeto Orquestracao Aguas Andinas
echo =====================================================
echo.

:: Verifica Python
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERRO] Python nao encontrado no PATH.
    echo        Instale Python 3.10+ em https://www.python.org/downloads/
    pause
    exit /b 1
)

for /f "tokens=2 delims= " %%v in ('python --version 2^>^&1') do set PY_VER=%%v
echo Python encontrado: %PY_VER%

:: Cria venv na raiz do projeto
if exist venv (
    echo [OK] venv ja existe, pulando criacao.
) else (
    echo Criando ambiente virtual em .\venv ...
    python -m venv venv
    if errorlevel 1 (
        echo [ERRO] Falha ao criar venv.
        pause
        exit /b 1
    )
    echo [OK] venv criado.
)

:: Ativa venv e instala dependencias
echo.
echo Instalando dependencias (requirements.txt)...
call venv\Scripts\activate.bat
python -m pip install --upgrade pip --quiet
pip install -r requirements.txt

if errorlevel 1 (
    echo.
    echo [ERRO] Falha na instalacao das dependencias.
    pause
    exit /b 1
)

echo.
echo =====================================================
echo  Setup concluido com sucesso!
echo.
echo  Para rodar a MACRO:
echo    venv\Scripts\activate
echo    python macro\valida_dados_aguasandinas_v2.1\executar_db.py
echo.
echo  Para rodar o DASHBOARD:
echo    venv\Scripts\activate
echo    cd dashboard_macros
echo    python run_dashboard.py
echo =====================================================
echo.
pause
