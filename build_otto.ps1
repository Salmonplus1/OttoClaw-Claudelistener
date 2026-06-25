# OttoClaw build script — ESP-IDF v5.5 + ESP32-S3
Remove-Item Env:MSYSTEM -ErrorAction SilentlyContinue
Remove-Item Env:MSYS -ErrorAction SilentlyContinue
Remove-Item Env:SHELL -ErrorAction SilentlyContinue

$env:IDF_PATH = 'C:\Users\qq482\esp\esp-idf-v5.5'
$env:IDF_PYTHON_ENV_PATH = 'C:\Users\qq482\.espressif\python_env\idf5.5_py3.12_env'

$tools = 'C:\Users\qq482\.espressif\tools'
$env:PATH = @(
    "$env:IDF_PYTHON_ENV_PATH\Scripts",
    "$tools\cmake\3.30.2\bin",
    "$tools\ninja\1.12.1",
    # Use toolchain version that matches ESP-IDF v5.5 requirement
    "$tools\xtensa-esp-elf\esp-14.2.0_20251107\xtensa-esp-elf\bin",
    'C:\Program Files\Git\bin',  # for git
    'C:\Windows\System32',
    'C:\Windows',
    'C:\Windows\System32\Wbem'
) -join ';'

Set-Location 'd:\OTTOrobot\OttoClaw-main\OttoClaw-main'

Write-Host "=== Step 1: Set target to ESP32-S3 ==="
python "$env:IDF_PATH\tools\idf.py" set-target esp32s3 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host "ERROR: set-target failed" -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "=== Step 2: Build ==="
python "$env:IDF_PATH\tools\idf.py" build 2>&1
