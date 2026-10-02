# Phase 4A only: init/validate/plan. This script has NO apply/destroy capability.
[CmdletBinding()]
param(
    [Parameter(Mandatory)][string]$VarFile,
    [Parameter(Mandatory)][string]$BackendConfig,
    [string]$Profile = 'camgiacntn',
    [ValidateSet('full', 'bootstrap')][string]$Scope = 'full'
)
$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path $PSScriptRoot -Parent
$tfRoot = Join-Path $repoRoot 'infrastructure\benchmark'
$varsPath = (Resolve-Path -LiteralPath $VarFile).Path
$backendPath = (Resolve-Path -LiteralPath $BackendConfig).Path
# Reject implicit inputs/options that could override the reviewed command.
foreach ($entry in Get-ChildItem Env:) {
    if ($entry.Name -match '^TF_(VAR_|CLI_ARGS|WORKSPACE|DATA_DIR|CLI_CONFIG_FILE)' -or $entry.Name -eq 'TF_CLI_CONFIG_FILE') {
        throw 'Remove Terraform environment overrides before planning.'
    }
}
if (Get-ChildItem -LiteralPath $tfRoot -File | Where-Object { $_.Name -match '^(terraform\.tfvars(?:\.json)?|.*\.auto\.tfvars(?:\.json)?|(?:.*_)?override\.tf(?:\.json)?)$' }) {
    throw 'Implicit tfvars/override files are forbidden; use the explicit benchmark var-file.'
}
$envNames = @('AWS_ACCESS_KEY_ID', 'AWS_SECRET_ACCESS_KEY', 'AWS_SESSION_TOKEN', 'AWS_PROFILE', 'AWS_DEFAULT_PROFILE')
$prior = @{}
foreach ($name in $envNames) { $prior[$name] = [Environment]::GetEnvironmentVariable($name, 'Process') }
Push-Location $repoRoot
try {
    python tools/benchmark_preflight.py --mode design --profile $Profile --var-file $varsPath --backend-config $backendPath
    if ($LASTEXITCODE -ne 0) { throw 'Preflight failed; stop before init.' }
    # CLI login credentials are not supported by the older Terraform SDK.
    # Export into this process only. Never print, persist or pass keys as Terraform variables.
    $credentialText = & aws configure export-credentials --profile $Profile --format process 2>$null
    if ($LASTEXITCODE -ne 0) { throw 'Credential export failed.' }
    $creds = ($credentialText -join "`n") | ConvertFrom-Json
    $env:AWS_ACCESS_KEY_ID = $creds.AccessKeyId
    $env:AWS_SECRET_ACCESS_KEY = $creds.SecretAccessKey
    $env:AWS_SESSION_TOKEN = $creds.SessionToken
    [Environment]::SetEnvironmentVariable('AWS_PROFILE', $null, 'Process')
    [Environment]::SetEnvironmentVariable('AWS_DEFAULT_PROFILE', $null, 'Process')
    $creds = $null
    $credentialText = $null
    & terraform "-chdir=$tfRoot" init -input=false -no-color "-backend-config=$backendPath"
    if ($LASTEXITCODE -ne 0) { throw 'Benchmark init failed.' }
    python tools/benchmark_preflight.py --mode design --profile $Profile --var-file $varsPath --backend-config $backendPath
    if ($LASTEXITCODE -ne 0) { throw 'Initialized backend does not pass preflight.' }
    & terraform "-chdir=$tfRoot" validate -no-color
    if ($LASTEXITCODE -ne 0) { throw 'Benchmark validate failed.' }
    $stem = if ($Scope -eq 'bootstrap') { 'benchmark-bootstrap' } else { 'benchmark' }
    $planPath = Join-Path $tfRoot ".terraform\$stem.tfplan"
    $planArgs = @("-chdir=$tfRoot", 'plan', '-input=false', '-no-color', "-var-file=$varsPath", "-out=$planPath")
    if ($Scope -eq 'bootstrap') {
        $planArgs += @('-target=aws_ecr_repository.benchmark', '-target=aws_acm_certificate.benchmark')
    }
    $planLines = & terraform @planArgs
    if ($LASTEXITCODE -ne 0) { throw 'Benchmark plan failed.' }
    [IO.File]::WriteAllText((Join-Path $tfRoot ".terraform\$stem-plan.txt"), ($planLines -join "`n"), [Text.UTF8Encoding]::new($false))
    $planLines | Select-String -Pattern '^Plan:' | ForEach-Object { Write-Output $_.Line }
    $planLines = $null
    $planJson = & terraform "-chdir=$tfRoot" show -json $planPath
    if ($LASTEXITCODE -ne 0) { throw 'Plan export failed.' }
    $jsonPath = Join-Path $tfRoot ".terraform\$stem-plan.json"
    [IO.File]::WriteAllText($jsonPath, ($planJson -join "`n"), [Text.UTF8Encoding]::new($false))
    $planJson = $null
    python tools/benchmark_preflight.py --mode design --scope $Scope --profile $Profile --var-file $varsPath --backend-config $backendPath --plan-json $jsonPath
    if ($LASTEXITCODE -ne 0) { throw 'Plan isolation guard failed; NO-GO.' }
    Write-Output 'Plan reviewed by automated isolation checks only. No apply performed.'
}
finally {
    foreach ($name in $envNames) { [Environment]::SetEnvironmentVariable($name, $prior[$name], 'Process') }
    $creds = $null
    $credentialText = $null
    Pop-Location
}
