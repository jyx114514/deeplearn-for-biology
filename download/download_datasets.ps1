$ErrorActionPreference='Stop'
$root=$PSScriptRoot
$base='https://assets.deep-learning-for-biology.com/'
$manifest=Invoke-RestMethod ($base+'urls.txt') -TimeoutSec 60
$manifest | Set-Content -LiteralPath (Join-Path $root 'source_urls.txt') -Encoding utf8
$chapters=@{dna='chapter_03_dna';graphs='chapter_04_graphs';localization='chapter_06_localization'}
$records=@()
foreach($line in ($manifest -split "`n")) {
 if($line.Trim() -notmatch '^(\d+)\s+((dna|graphs|localization)/datasets/(.+))$'){continue}
 $size=[long]$Matches[1];$remote=$Matches[2];$chapter=$Matches[3];$relative=$Matches[4]
 $dest=Join-Path (Join-Path $root $chapters[$chapter]) $relative
 New-Item -ItemType Directory -Path (Split-Path -Parent $dest) -Force | Out-Null
 $records += [pscustomobject]@{path=$dest;url=$base+$remote;expected_bytes=$size}
}
$records | ConvertTo-Json -Depth 3 | Set-Content -LiteralPath (Join-Path $root 'download_manifest.json') -Encoding utf8
# Fetch smaller files first so the large image array does not delay other chapters.
foreach($r in ($records | Sort-Object expected_bytes)) {
 if((Test-Path -LiteralPath $r.path) -and (Get-Item -LiteralPath $r.path).Length -eq $r.expected_bytes){Write-Output "SKIP $($r.path)";continue}
 if ($r.path.EndsWith('images.npy') -and (Test-Path -LiteralPath (Join-Path $root 'chapter_06_localization\images.npy.ranges.json'))) { throw 'Parallel download state exists; resume with download_images_parallel.py using the project virtual environment.' }
 $partial=$r.path+'.part'
 Write-Output "DOWNLOAD $($r.url) EXPECTED $($r.expected_bytes)"
 & curl.exe --fail --location --retry 8 --retry-delay 5 --connect-timeout 30 --speed-limit 1024 --speed-time 120 --continue-at - --output $partial --silent --show-error $r.url
 if($LASTEXITCODE -ne 0){throw "curl failed: $($r.url) exit=$LASTEXITCODE"}
 $actual=(Get-Item -LiteralPath $partial).Length
 if($actual -ne $r.expected_bytes){throw "Size mismatch: $($r.path) expected=$($r.expected_bytes) actual=$actual"}
 Move-Item -LiteralPath $partial -Destination $r.path -Force
 Write-Output "VERIFIED $($r.path) $actual bytes"
}
Write-Output 'ALL_DOWNLOADS_COMPLETE'

