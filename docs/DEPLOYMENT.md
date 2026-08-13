# Deployment Strategy

## Platform
- **Target**: Render or Railway (PaaS).
- **Reason**: Both offer seamless deployment for Python web apps directly from a Git repository, handle HTTPS automatically, and provide easy environment variable management.

## Environments
1. **Development**: Local machine, local `.env`, testing against a development Google Sheet. Uses placeholder API keys in Phase 1.
2. **Staging**: Pre-production environment for User Acceptance Testing (UAT). Connects to a staging Google Sheet.
3. **Production**: Hosted on Render/Railway, production environment variables, writing to the live Google Sheet.

## Configuration
- `Procfile` or start command configured for FastAPI (e.g., `uvicorn main:app --host 0.0.0.0 --port $PORT`).
- `requirements.txt` strictly pinned with versions.
- Health check endpoint (`/health`) for the PaaS to monitor uptime.

## Render Sleep Mode
- Free tier on Render spins down after 15 minutes of inactivity. The user must be aware that the first request after a period of inactivity may take 30-50 seconds.
- Background tasks (like reminders) cannot rely on a sleeping instance. Overdue tasks are calculated dynamically upon page load.

## Rollback
- Since state is external (Google Sheets), rolling back the application code via Render/Railway dashboard is safe and will not result in data loss.
