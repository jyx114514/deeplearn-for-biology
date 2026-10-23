$ErrorActionPreference='Stop'
$root=$PSScriptRoot
$python='D:\bio_statistics\protein_learning\.venv\Scripts\python.exe'
try {
 & $python -u (Join-Path $root 'download_images_parallel.py')
 if($LASTEXITCODE -ne 0){throw "Image downloader exit $LASTEXITCODE"}
 & $python -u (Join-Path $root 'verify_datasets.py')
 if($LASTEXITCODE -ne 0){throw "Verification exit $LASTEXITCODE"}
 'ALL_DATASETS_DOWNLOADED_AND_VERIFIED' | Set-Content -LiteralPath (Join-Path $root 'COMPLETE.txt') -Encoding utf8
} catch {
 $_ | Out-String | Set-Content -LiteralPath (Join-Path $root 'download_error.txt') -Encoding utf8
 throw
}
