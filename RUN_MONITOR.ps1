param(
    [Parameter(Mandatory=$true)][string]$Feed,
    [string]$OutputDirectory = "$PSScriptRoot\outputs",
    [string]$Session = "",
    [switch]$Historical,
    [string]$Context = "",
    [string]$Positions = "",
    [string]$Benchmarks = ""
)
$ErrorActionPreference = "Stop"
$runtimeRoot = Join-Path $env:USERPROFILE '.cache\codex-runtimes\codex-primary-runtime\dependencies'
$pythonExe = Join-Path $runtimeRoot 'python\python.exe'
$nodeExe = Join-Path $runtimeRoot 'node\bin\node.exe'
if (!(Test-Path $pythonExe) -or !(Test-Path $nodeExe)) { throw 'Codex bundled Python and Node runtimes required' }
$localDeps = Join-Path $PSScriptRoot '.runtime'
if (!(Test-Path (Join-Path $localDeps 'exchange_calendars'))) {
    & $pythonExe -m pip install --target $localDeps -r (Join-Path $PSScriptRoot 'requirements-monitor.txt')
    if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed' }
}
$env:PYTHONPATH = $localDeps
if (!(Test-Path (Join-Path $PSScriptRoot 'node_modules'))) {
    New-Item -ItemType Junction -Path (Join-Path $PSScriptRoot 'node_modules') -Target (Join-Path $runtimeRoot 'node\node_modules') | Out-Null
}
New-Item -ItemType Directory -Path $OutputDirectory -Force | Out-Null
$dataPath = Join-Path $OutputDirectory 'monitor_results.json'
$argsMonitor = @((Join-Path $PSScriptRoot 'buy_sell_monitor.py'), '--feed', $Feed, '--universe', (Join-Path $PSScriptRoot 'tickers.csv'), '--output', $dataPath)
if ($Session) { $argsMonitor += @('--session', $Session) }
if ($Historical) { $argsMonitor += '--historical' }
foreach ($item in @(@('context',$Context),@('positions',$Positions),@('benchmarks',$Benchmarks))) {
    if ($item[1]) { $argsMonitor += @('--'+$item[0],$item[1]) }
}
& $pythonExe @argsMonitor
if ($LASTEXITCODE -ne 0) { throw 'Monitor validation/calculation failed; workbook not exported' }
$reportData = Get-Content -Raw $dataPath | ConvertFrom-Json
$reportPath = Join-Path $OutputDirectory ("Stock_Buy_Sell_Monitor_"+$reportData.session+$(if ($Historical) {'_REVISED_HISTORICAL'} else {'_REVISED'})+'.xlsx')
& $nodeExe (Join-Path $PSScriptRoot 'export_monitor.mjs') $dataPath $reportPath
if ($LASTEXITCODE -ne 0) { throw 'Workbook export failed' }
Write-Output $reportPath
