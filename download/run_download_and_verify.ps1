# Compatibility entry: now downloads/resumes ALL selected chapters, then verifies.
# All parameters are forwarded to the main entry point.
& (Join-Path $PSScriptRoot 'download_datasets.ps1') @args
