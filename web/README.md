# Django console (portfolio)

Django UI on port **8001**. FastAPI on **8000** is unchanged (`GET /health`, `POST /optimize-energy`).

```powershell
cd web
python -m pip install -r requirements.txt
copy .env.example .env
python manage.py migrate
python manage.py runserver 8001
```

Open http://127.0.0.1:8001/accounts/register

Postgres via compose: from the repo root, `docker compose up --build` then Django at http://127.0.0.1:8001 and the API at http://127.0.0.1:8000.

Without `DATABASE_URL`, Django uses local SQLite (`web/db.sqlite3`).
