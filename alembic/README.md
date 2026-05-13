# Alembic migrations

- env.py вже налаштовано для імпорту моделей з app.models
- Для створення бази даних використовуйте:
  python -m app.database create-db
- Для створення початкової міграції використовуйте:
  alembic revision --autogenerate -m "init"
- Для застосування міграцій:
  alembic upgrade head

.env має містити налаштування для підключення до бази (DB_USER, DB_PASS, DB_HOST, DB_PORT, DB_NAME)
