$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
$exe = Join-Path $PSScriptRoot 'go2rtc.exe'
if (-not (Test-Path $exe)) {
    $zip = Join-Path $PSScriptRoot 'go2rtc.zip'
    Invoke-WebRequest -Uri 'https://github.com/AlexxIT/go2rtc/releases/latest/download/go2rtc_win64.zip' -OutFile $zip
    Expand-Archive -Path $zip -DestinationPath $PSScriptRoot -Force
    Remove-Item $zip
}
$config = Join-Path $PSScriptRoot 'go2rtc.yaml'
if (-not (Test-Path $config)) {
    $config = Join-Path $PSScriptRoot 'go2rtc.example.yaml'
}
& $exe -config $config
