# Local-only image validation. Never logs into ECR, pushes, deploys or runs the app.
[CmdletBinding()]
param([Parameter(Mandatory)][ValidatePattern('^[0-9a-f]{40}$')][string]$ImageGitSha)
$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path $PSScriptRoot -Parent
Push-Location $repoRoot
try {
    $head = (& git rev-parse HEAD).Trim()
    if ($LASTEXITCODE -ne 0 -or $head -ne $ImageGitSha) { throw 'Image source must be current full HEAD SHA.' }
    $dirty = & git status --porcelain --untracked-files=all
    if ($LASTEXITCODE -ne 0 -or $dirty) { throw 'Build requires an isolated clean checkpoint, including untracked files.' }
    $dockerVersion = & docker version --format '{{.Server.Version}}' 2>$null
    if ($LASTEXITCODE -ne 0 -or -not $dockerVersion) { throw 'Docker daemon unavailable.' }
    $tag = "livecap-benchmark-validation:$ImageGitSha-amd64"
    & docker build --platform linux/amd64 --label "org.opencontainers.image.revision=$ImageGitSha" -t $tag backend
    if ($LASTEXITCODE -ne 0) { throw 'Local image build failed.' }
    $image = (& docker image inspect $tag | ConvertFrom-Json)[0]
    if ($LASTEXITCODE -ne 0 -or $image.Os -ne 'linux' -or $image.Architecture -ne 'amd64' -or $image.Config.Labels.'org.opencontainers.image.revision' -ne $ImageGitSha) {
        throw 'Image platform/source metadata mismatch.'
    }
    $check = @'
import sys, json, compileall, boto3, fastapi, watchtower
from amazon_transcribe.client import TranscribeStreamingClient
from pathlib import Path
assert sys.version_info[:2] == (3, 11)
assert compileall.compile_dir('/app/app', quiet=1)
events = ['websocket_admission_completed', 'transcribe_stream_started', 'transcribe_result_received', 'translation_operation_completed', 'arbitration_or_buffer_completed', 'websocket_caption_send_completed', 'websocket_session_outcome']
source = ''.join(p.read_text() for p in Path('/app/app').rglob('*.py'))
assert all(event in source for event in events)
print(json.dumps({'python': sys.version.split()[0], 'compileall': 'passed', 'dependency_imports': 'passed', 'event_names_present': len(events)}))
'@
    $validation = & docker run --rm --network none --entrypoint python $tag -c $check
    if ($LASTEXITCODE -ne 0) { throw 'Offline image validation failed.' }
    $runtime = ($validation -join "`n") | ConvertFrom-Json
    & docker run --rm --network none --entrypoint python $tag -m pip check
    if ($LASTEXITCODE -ne 0) { throw 'Image dependency conflict.' }
    $artifactDirectory = Join-Path $repoRoot 'infrastructure\benchmark\.terraform'
    New-Item -ItemType Directory -Path $artifactDirectory -Force | Out-Null
    $evidence = [ordered]@{
        evidence_type = 'local-offline-image-validation-not-performance-or-deployment'
        validated_at_utc = [DateTime]::UtcNow.ToString('o')
        source_sha = $ImageGitSha
        backend_git_tree = (& git rev-parse 'HEAD:backend').Trim()
        image_tag = $tag
        local_image_id = $image.Id
        remote_ecr_digest_verified = $false
        os = $image.Os
        architecture = $image.Architecture
        runtime = $runtime
        pip_check = 'passed'
        validation_network = 'none'
        credentials_passed_to_container = $false
        pushed = $false
        deployed = $false
        limitations = @('Event name presence is not pipeline execution evidence.', 'Build dependencies may use existing Docker cache.', 'Local image ID is not the remote ECR digest.')
    }
    $manifest = Join-Path $artifactDirectory 'benchmark-image-validation.json'
    [IO.File]::WriteAllText($manifest, ($evidence | ConvertTo-Json -Depth 5) + "`n", [Text.UTF8Encoding]::new($false))
    Write-Output "Local image verified; evidence: $manifest"
}
finally { Pop-Location }
