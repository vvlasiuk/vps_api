@echo off
REM Активація venv та запуск сервісу
if not exist venv\Scripts\activate.bat (
    echo Віртуальне середовище не знайдено. Запустіть setup.bat
    exit /b 1
)
call venv\Scripts\activate.bat
@REM python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
python -m uvicorn app.main:app --env-file .env --host 0.0.0.0 --port 8000 --reload


