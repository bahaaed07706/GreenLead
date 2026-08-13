$ErrorActionPreference = "Stop"

if (-Not (Test-Path ".venv\Scripts\python.exe")) {
    Write-Error "Virtual environment not found. Please run 'python -m venv .venv' and install dependencies."
    exit 1
}

Write-Host "Starting GreenLead development server..."
& .\.venv\Scripts\python.exe -m uvicorn greenlead.main:app --reload --host 127.0.0.1 --port 8000
