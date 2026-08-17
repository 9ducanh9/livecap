param(
    [Parameter(Mandatory = $true)]
    [string]$Bucket,

    [Parameter(Mandatory = $true)]
    [string]$DistributionId,

    [string]$BuildDirectory = (Join-Path $PSScriptRoot "..\frontend\dist")
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$resolvedBuildDirectory = (Resolve-Path -LiteralPath $BuildDirectory).Path
if (-not (Test-Path -LiteralPath (Join-Path $resolvedBuildDirectory "index.html"))) {
    throw "Build directory does not contain index.html: $resolvedBuildDirectory"
}

# Keep Vite's content-hashed assets available for clients with older HTML.
$assetsDirectory = Join-Path $resolvedBuildDirectory "assets"
if (Test-Path -LiteralPath $assetsDirectory) {
    aws s3 cp "$assetsDirectory/" "s3://$Bucket/assets/" `
        --recursive `
        --cache-control "public,max-age=31536000,immutable"
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to upload content-hashed frontend assets."
    }
}

# Fixed-name resources and SPA entry documents must always revalidate.
aws s3 cp "$resolvedBuildDirectory/" "s3://$Bucket/" `
    --recursive `
    --exclude "assets/*" `
    --exclude "*.html" `
    --cache-control "no-cache,must-revalidate"
if ($LASTEXITCODE -ne 0) {
    throw "Failed to upload fixed-name frontend resources."
}

aws s3 cp "$resolvedBuildDirectory/" "s3://$Bucket/" `
    --recursive `
    --exclude "*" `
    --include "*.html" `
    --cache-control "no-cache,no-store,must-revalidate"
if ($LASTEXITCODE -ne 0) {
    throw "Failed to upload frontend HTML."
}

$invalidationId = aws cloudfront create-invalidation `
    --distribution-id $DistributionId `
    --paths "/*" `
    --query "Invalidation.Id" `
    --output text
if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($invalidationId)) {
    throw "Failed to create CloudFront invalidation."
}

aws cloudfront wait invalidation-completed `
    --distribution-id $DistributionId `
    --id $invalidationId
if ($LASTEXITCODE -ne 0) {
    throw "CloudFront invalidation did not complete successfully."
}

Write-Host "Frontend deployed. CloudFront invalidation completed: $invalidationId"
