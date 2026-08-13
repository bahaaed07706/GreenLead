$ErrorActionPreference = "Stop"

if (-Not (Test-Path ".venv\Scripts\python.exe")) {
    Write-Error "Virtual environment not found. Please run 'python -m venv .venv' and install dependencies."
    exit 1
}

Write-Host "Running Ruff Check..."
& .\.venv\Scripts\python.exe -m ruff check .
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "Running Ruff Format Check..."
& .\.venv\Scripts\python.exe -m ruff format --check .
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "Running Mypy..."
& .\.venv\Scripts\python.exe -m mypy src
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "All quality checks passed!"
