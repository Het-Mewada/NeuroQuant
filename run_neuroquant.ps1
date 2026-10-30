# Project NeuroQuant - Dual Runner Script
Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "   Starting NeuroQuant Autonomous Trading Platform        " -ForegroundColor Yellow
Write-Host "==========================================================" -ForegroundColor Cyan

# Check backend
Write-Host "`n[1/2] Launching Python Backend on http://localhost:8000..." -ForegroundColor Green
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd backend; uv run uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload"

# Check frontend
Write-Host "[2/2] Launching React Financial Dashboard on http://localhost:5173..." -ForegroundColor Green
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd frontend; npm run dev"

Write-Host "`nBoth services launched in separate windows!" -ForegroundColor Cyan
Write-Host "Dashboard URL: http://localhost:5173" -ForegroundColor White
Write-Host "API Swagger URL: http://localhost:8000/docs" -ForegroundColor White
Write-Host "WebSocket Feed: ws://localhost:8000/ws/telemetry" -ForegroundColor White
