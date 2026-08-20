$ErrorActionPreference = 'Stop'
$project = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location -LiteralPath $project

$python = (Get-Command python -ErrorAction SilentlyContinue).Source
if (-not $python) {
    $python = (Get-Command py -ErrorAction SilentlyContinue).Source
}
if (-not $python) {
    throw '未找到Python。请安装带Tcl/Tk的Python 3.11或更高版本。'
}

& $python -m PyInstaller --noconfirm --clean --onefile --windowed `
    --name '晒_双角色规则测试器' `
    --distpath 'dist' `
    --workpath 'build\work' `
    --specpath 'build' `
    'main.py'

Write-Host '构建完成：dist\晒_双角色规则测试器.exe'
