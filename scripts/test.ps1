$ErrorActionPreference = "Stop"

if (-Not (Test-Path ".venv\Scripts\python.exe")) {
    Write-Error "Virtual environment not found. Please run 'python -m venv .venv' and install dependencies."
    exit 1
}

Write-Host "Running tests with coverage..."
$env:PYTHONPATH = "$PWD\src"
& .\.venv\Scripts\python.exe -m pytest --cov=greenlead --cov-report=term-missing
if ($LASTEXITCODE -ne 0) {
    Write-Error "Tests failed!"
    exit $LASTEXITCODE
}
Write-Host "Tests passed successfully."
