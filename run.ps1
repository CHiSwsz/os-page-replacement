# Requires CMake and a C++17 compiler (Visual Studio Build Tools or MinGW).
$ErrorActionPreference = 'Stop'
if ($args.Count -eq 0) { Write-Error 'Usage: .\run.ps1 TRACE.txt [--format json]'; exit 2 }
$projectDir = $PSScriptRoot
cmake -S $projectDir -B "$projectDir/build-live" -DCMAKE_BUILD_TYPE=Release -DBUILD_TESTING=OFF | Out-Host
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
cmake --build "$projectDir/build-live" --config Release -j 4 | Out-Host
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
$pager = Join-Path $projectDir 'build-live/Release/pager.exe'
if (!(Test-Path $pager)) { $pager = Join-Path $projectDir 'build-live/pager.exe' }
& $pager --contest @args
exit $LASTEXITCODE
