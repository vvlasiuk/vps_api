cd /d "%~dp0"
"%~dp0venv\Scripts\Python.exe" -m uvicorn "app.main:app" --env-file "%~dp0.env" --host 0.0.0.0 --port 8000 --reload