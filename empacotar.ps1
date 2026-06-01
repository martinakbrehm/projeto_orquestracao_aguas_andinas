# =============================================================================
# empacotar.ps1 — Gera ZIP com os arquivos essenciais do projeto
#
# Uso: clique com botao direito > "Executar com PowerShell"
#      ou no terminal:  .\empacotar.ps1
#
# O ZIP e gerado na raiz do projeto como:
#   projeto_orquestracao_aguas_andinas_AAAAMMDD.zip
# =============================================================================

$ErrorActionPreference = "Stop"

# Pasta raiz do projeto (onde este script esta)
$ROOT = Split-Path -Parent $MyInvocation.MyCommand.Path

# Nome e destino do ZIP
$DATA   = Get-Date -Format "yyyyMMdd"
$NOME   = "projeto_orquestracao_aguas_andinas_$DATA"
$TMPDIR = Join-Path $env:TEMP $NOME
$ZIPOUT = Join-Path $ROOT "$NOME.zip"

Write-Host ""
Write-Host "=============================================" -ForegroundColor Cyan
Write-Host " Empacotando projeto Aguas Andinas..." -ForegroundColor Cyan
Write-Host "=============================================" -ForegroundColor Cyan
Write-Host ""

# Remove diretorio temporario anterior se existir
if (Test-Path $TMPDIR) { Remove-Item $TMPDIR -Recurse -Force }
New-Item -ItemType Directory -Path $TMPDIR | Out-Null

# ------------------------------------------------------------------
# Funcao auxiliar: copia arquivo preservando estrutura de diretorios
# ------------------------------------------------------------------
function CopiarArquivo($origem, $destBase, $prefixoRelativo) {
    $relativo  = $origem.FullName.Substring($prefixoRelativo.Length).TrimStart('\','/')
    $destFinal = Join-Path $destBase $relativo
    $destDir   = Split-Path $destFinal
    if (-not (Test-Path $destDir)) { New-Item -ItemType Directory -Path $destDir -Force | Out-Null }
    Copy-Item $origem.FullName -Destination $destFinal -Force
}

$prefixo = $ROOT + "\"

# ------------------------------------------------------------------
# Arquivos da RAIZ
# ------------------------------------------------------------------
$arquivosRaiz = @(
    "config.py",
    "config.example.py",
    "requirements.txt",
    "setup.bat",
    "setup.sh",
    "INSTRUCOES.md",
    "README.md"
)

foreach ($arq in $arquivosRaiz) {
    $caminho = Join-Path $ROOT $arq
    if (Test-Path $caminho) {
        Copy-Item $caminho -Destination (Join-Path $TMPDIR $arq) -Force
        Write-Host "  [OK] $arq"
    } else {
        Write-Host "  [--] $arq (nao encontrado, pulando)"
    }
}

# ------------------------------------------------------------------
# Macro — apenas os arquivos necessarios para executar_db.py
# ------------------------------------------------------------------
$arquivosMacro = @(
    "macro\valida_dados_aguasandinas_v2.1\executar_db.py",
    "macro\valida_dados_aguasandinas_v2.1\config.py",     # inclui db_aguas_andinas()
    "macro\valida_dados_aguasandinas_v2.1\requirements.txt",
    "macro\valida_dados_aguasandinas_v2.1\core\extrator.py"
)

foreach ($arq in $arquivosMacro) {
    $caminho = Join-Path $ROOT $arq
    if (Test-Path $caminho) {
        $dest = Join-Path $TMPDIR $arq
        $dir  = Split-Path $dest
        if (-not (Test-Path $dir)) { New-Item -ItemType Directory -Path $dir -Force | Out-Null }
        Copy-Item $caminho -Destination $dest -Force
        Write-Host "  [OK] $arq"
    } else {
        Write-Host "  [--] $arq (nao encontrado, pulando)"
    }
}

# ------------------------------------------------------------------
# ETL — apenas interpretar_resposta_aa (dependencia da macro)
# ------------------------------------------------------------------
$arquivosEtl = @(
    "etl\transformation\macro_aa\__init__.py",
    "etl\transformation\macro_aa\interpretar_resposta_aa.py"
)

foreach ($arq in $arquivosEtl) {
    $caminho = Join-Path $ROOT $arq
    if (Test-Path $caminho) {
        $dest = Join-Path $TMPDIR $arq
        $dir  = Split-Path $dest
        if (-not (Test-Path $dir)) { New-Item -ItemType Directory -Path $dir -Force | Out-Null }
        Copy-Item $caminho -Destination $dest -Force
        Write-Host "  [OK] $arq"
    } else {
        Write-Host "  [--] $arq (nao encontrado, pulando)"
    }
}

# ------------------------------------------------------------------
# Dashboard — apenas arquivos essenciais para rodar (sem docs, bats, duplicatas)
# ------------------------------------------------------------------
$pastaDash  = Join-Path $ROOT "dashboard_macros"
$destDash   = Join-Path $TMPDIR "dashboard_macros"

# Nomes de arquivo (exatos) a excluir do dashboard_macros
$excluirArquivos = @(
    "DOCUMENTACAO_DASHBOARD.md",
    "INSTRUCOES_SERVIDOR.md",
    "README_AUTH.md",
    "iniciar_dashboard.bat",
    "iniciar_refresh.bat",
    "run_dashboard.bat",
    "run_dashboard_launcher.py",
    "setup_dashboard.bat",
    "setup_dashboard.py",
    "requirements.txt"         # ja consolidado no requirements.txt da raiz
)

Get-ChildItem -Path $pastaDash -Recurse -File | Where-Object {
    $caminho = $_.FullName

    $excluir = $false

    # Exclui pastas de cache/venv em qualquer nivel
    foreach ($exc in @("__pycache__", "venv", ".venv")) {
        if ($caminho -match [regex]::Escape($exc)) { $excluir = $true; break }
    }
    # Exclui .pyc/.pyo
    if ($_.Extension -in @(".pyc", ".pyo")) { $excluir = $true }
    # Exclui arquivos desnecessarios pelo nome exato
    if ($_.Name -in $excluirArquivos) { $excluir = $true }

    -not $excluir
} | ForEach-Object {
    $relativo  = $_.FullName.Substring(($ROOT + "\").Length)
    $dest      = Join-Path $TMPDIR $relativo
    $dir       = Split-Path $dest
    if (-not (Test-Path $dir)) { New-Item -ItemType Directory -Path $dir -Force | Out-Null }
    Copy-Item $_.FullName -Destination $dest -Force
    Write-Host "  [OK] $relativo"
}

# ------------------------------------------------------------------
# Gera o ZIP
# ------------------------------------------------------------------
Write-Host ""
Write-Host "Gerando ZIP em: $ZIPOUT" -ForegroundColor Yellow

if (Test-Path $ZIPOUT) { Remove-Item $ZIPOUT -Force }

Compress-Archive -Path "$TMPDIR\*" -DestinationPath $ZIPOUT -CompressionLevel Optimal

# Limpeza do temporario
Remove-Item $TMPDIR -Recurse -Force

# Resultado
$tamanho = (Get-Item $ZIPOUT).Length / 1KB
Write-Host ""
Write-Host "=============================================" -ForegroundColor Green
Write-Host " ZIP gerado com sucesso!" -ForegroundColor Green
Write-Host " Arquivo : $ZIPOUT" -ForegroundColor Green
Write-Host " Tamanho : $([math]::Round($tamanho, 1)) KB" -ForegroundColor Green
Write-Host "=============================================" -ForegroundColor Green
Write-Host ""
