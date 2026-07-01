# Car Ads Dashboard

Django dashboard for viewing and maintaining car ads data. The dashboard reads the same PostgreSQL database used by the scraper/FastAPI project through Django ORM models, not through the FastAPI API.

## Stack

- Python 3.12
- Django 5.2
- PostgreSQL
- Redis
- Django Channels + Daphne for WebSocket log streaming
- Celery for background jobs

## Main features

- User login, registration, approval, and role management
- Admin and user dashboards for car listing analytics
- Cars Standard maintenance UI and background jobs
- Server metrics and log viewer
- Data archiving helper script

## Project layout

```text
.
├── requirements.txt
├── car_ads_dashboard/
│   ├── manage.py
│   ├── data_archiver.py
│   ├── .env.example
│   ├── car_ads_dashboard/
│   │   ├── settings.py
│   │   ├── asgi.py
│   │   ├── celery.py
│   │   └── urls.py
│   └── dashboard/
│       ├── models.py
│       ├── views.py
│       ├── tasks.py
│       ├── consumers.py
│       ├── routing.py
│       ├── services/
│       └── management/commands/
└── logs/
```

## Requirements

Install these on the server or development machine:

- Python 3.12+
- PostgreSQL
- Redis server
- `tail` command, used by the WebSocket log viewer

On Ubuntu/Debian:

```bash
sudo apt update
sudo apt install python3 python3-venv python3-pip postgresql redis-server
```

## Environment variables

Copy the example file and adjust it:

```bash
cd car_ads_dashboard
cp .env.example .env
```

Example:

```env
SECRET_KEY=replace-with-a-strong-secret-key
DEBUG=True
ALLOWED_HOSTS=localhost,127.0.0.1
CSRF_TRUSTED_ORIGINS=http://localhost:8000,http://127.0.0.1:8000
DB_NAME=db_fastapi_scrap
DB_USER=postgres
DB_PASSWORD=change-me
DB_HOST=localhost
DB_PORT=5432
```

Notes:

- Run Django commands from `car_ads_dashboard/` so `settings.py` can load `car_ads_dashboard/.env`.
- `ALLOWED_HOSTS` and `CSRF_TRUSTED_ORIGINS` are comma-separated lists.
- For production, set `DEBUG=False`, use a strong `SECRET_KEY`, and set real hostnames/origins.
- Redis is currently hardcoded in `settings.py` as `localhost:6379`, database `0`, for both Channels and Celery.

## Development setup

From the repository root:

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cd car_ads_dashboard
cp .env.example .env
python manage.py migrate
python manage.py create_groups
python manage.py create_superadmin --username admin --email admin@example.com --password 'change-me'
```

Start Redis:

```bash
sudo systemctl enable --now redis-server
redis-cli ping
```

Expected output:

```text
PONG
```

Run the web app:

```bash
python manage.py runserver 0.0.0.0:8000
```

Run Celery in another terminal:

```bash
cd car_ads_dashboard
../venv/bin/celery -A car_ads_dashboard worker --loglevel=info
```

For WebSocket behavior closer to production, use Daphne instead of `runserver`:

```bash
cd car_ads_dashboard
../venv/bin/daphne -b 0.0.0.0 -p 8000 car_ads_dashboard.asgi:application
```

Open:

```text
http://127.0.0.1:8000/
```

## Database notes

This project uses PostgreSQL. Some models are unmanaged because their tables are owned by the scraper/FastAPI database schema, for example:

- `cars_standard`
- unified car listing tables
- price history tables

The dashboard migrations create dashboard-specific tables such as user profiles, audit logs, and maintenance jobs. The external scraper tables must already exist in the configured database.

## Redis, Channels, and Celery

Redis is used by two parts of the app:

1. Django Channels, for WebSocket channel layer.
2. Celery, for broker and result backend.

Current settings:

```python
CHANNEL_LAYERS -> 127.0.0.1:6379
CELERY_BROKER_URL -> redis://localhost:6379/0
CELERY_RESULT_BACKEND -> redis://localhost:6379/0
```

Development commands:

```bash
sudo systemctl start redis-server
cd car_ads_dashboard
../venv/bin/celery -A car_ads_dashboard worker --loglevel=info
../venv/bin/daphne -b 0.0.0.0 -p 8000 car_ads_dashboard.asgi:application
```

If Celery jobs stay pending, check:

```bash
redis-cli ping
cd car_ads_dashboard
../venv/bin/celery -A car_ads_dashboard inspect ping
```

## Production setup

A minimal production setup usually runs:

- PostgreSQL
- Redis
- Daphne ASGI app behind Nginx or another reverse proxy
- Celery worker

Install dependencies:

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cd car_ads_dashboard
cp .env.example .env
```

Set production values in `.env`:

```env
SECRET_KEY=use-a-long-random-secret
DEBUG=False
ALLOWED_HOSTS=your-domain.com,your-server-ip
CSRF_TRUSTED_ORIGINS=https://your-domain.com
DB_NAME=db_fastapi_scrap
DB_USER=dashboard_user
DB_PASSWORD=change-me
DB_HOST=localhost
DB_PORT=5432
```

Prepare Django:

```bash
cd car_ads_dashboard
../venv/bin/python manage.py migrate
../venv/bin/python manage.py collectstatic --noinput
../venv/bin/python manage.py create_groups
../venv/bin/python manage.py create_superadmin --username admin --email admin@example.com --password 'change-me'
```

Example systemd service for Daphne:

```ini
[Unit]
Description=Car Ads Dashboard Daphne
After=network.target postgresql.service redis-server.service

[Service]
User=www-data
Group=www-data
WorkingDirectory=/path/to/bdt_dashboard-scrap-result/car_ads_dashboard
Environment="DJANGO_SETTINGS_MODULE=car_ads_dashboard.settings"
ExecStart=/path/to/bdt_dashboard-scrap-result/venv/bin/daphne -b 127.0.0.1 -p 8000 car_ads_dashboard.asgi:application
Restart=always

[Install]
WantedBy=multi-user.target
```

Example systemd service for Celery:

```ini
[Unit]
Description=Car Ads Dashboard Celery Worker
After=network.target redis-server.service postgresql.service

[Service]
User=www-data
Group=www-data
WorkingDirectory=/path/to/bdt_dashboard-scrap-result/car_ads_dashboard
Environment="DJANGO_SETTINGS_MODULE=car_ads_dashboard.settings"
ExecStart=/path/to/bdt_dashboard-scrap-result/venv/bin/celery -A car_ads_dashboard worker --loglevel=info
Restart=always

[Install]
WantedBy=multi-user.target
```

Enable services:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now redis-server
sudo systemctl enable --now car-ads-dashboard.service
sudo systemctl enable --now car-ads-celery.service
```

Check logs:

```bash
sudo journalctl -u car-ads-dashboard.service -f
sudo journalctl -u car-ads-celery.service -f
```

## Useful management commands

Create default groups:

```bash
python manage.py create_groups
```

Create a super admin:

```bash
python manage.py create_superadmin --username admin --email admin@example.com --password 'change-me'
```

Create missing user profiles:

```bash
python manage.py create_user_profiles
```

Fix admin approval state:

```bash
python manage.py fix_admin_approval
```

Import Cars Standard data:

```bash
python manage.py import_carsstandard
```

## Data archiver

`data_archiver.py` archives old dashboard data into archive tables.

Run from `car_ads_dashboard/`:

```bash
python data_archiver.py --stats-only
python data_archiver.py --months 6 --dry-run
python data_archiver.py --months 6
python data_archiver.py --months 12 --auto-confirm
```

## Tests and checks

Run Django checks:

```bash
cd car_ads_dashboard
python manage.py check
```

Run tests:

```bash
cd car_ads_dashboard
python manage.py test dashboard
```

## Common issues

### Redis connection refused

Start Redis and verify it responds:

```bash
sudo systemctl start redis-server
redis-cli ping
```

### Celery task remains pending

Make sure the worker is running from `car_ads_dashboard/`:

```bash
../venv/bin/celery -A car_ads_dashboard worker --loglevel=info
```

### Static files missing in production

Run:

```bash
python manage.py collectstatic --noinput
```

Serve `staticfiles/` from the reverse proxy, or set `DJANGO_SERVE_STATIC=True` only for simple internal deployments.

### Login or CSRF errors after deployment

Check these values in `.env`:

```env
ALLOWED_HOSTS=your-domain.com,your-server-ip
CSRF_TRUSTED_ORIGINS=https://your-domain.com
DEBUG=False
```

### WebSocket log viewer cannot read logs

`dashboard/consumers.py` only allows specific log file paths and the service user must have read permission. Update the allowed paths in code or make the configured paths readable by the Daphne service user.
