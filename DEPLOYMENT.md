# Deploying Shekinah Blaze on cPanel (MariaDB)

Production domain: **shekinahblaze.org** · Settings module: `sboi.settings_prod`

The app runs under **Phusion Passenger** (cPanel's "Setup Python App"), stores
data in **MariaDB**, and serves static files and uploads from the account's
**`public_html`** directory.

---

## Which environment is "production"?

| | Local development | **Production (cPanel)** |
| --- | --- | --- |
| Settings module | `sboi.settings` | **`sboi.settings_prod`** |
| Config file | none | **`.env`** (copied from `.env.example`) |
| Database | SQLite (`db.sqlite3`) | **MariaDB** |
| `DEBUG` | `True` | `False` |
| Static / media | `static/`, `media/` | **`public_html/static`, `public_html/media`** |
| Served by | `runserver` | Passenger → `passenger_wsgi.py` |

**`.env.example` is only a template.** The real production configuration is the
`.env` file you create from it. `passenger_wsgi.py` always loads
`sboi.settings_prod`, which reads `.env` — so on the server you do **not** set
`DJANGO_SETTINGS_MODULE` by hand (except for one-off `manage.py` commands).

---

## 1. Create the database and user

1. cPanel → **MySQL® Databases**.
2. **Create New Database** — e.g. `sboi` (cPanel prefixes it → `myacct_sboi`).
3. **Add New User** — note the password (cPanel prefixes it → `myacct_sboiuser`).
4. **Add User To Database** → select the database → grant **ALL PRIVILEGES**.

Write down the full (prefixed) names and the password — they go into `.env`.

> The site only needs plain MariaDB. No extensions beyond the defaults are
> required.

## 2. Upload the code

Use cPanel → **Git™ Version Control** (recommended) or **File Manager** to put
the project **outside** `public_html`, e.g. `/home/myacct/sboi`.

Do **not** upload `.env`, `db.sqlite3`, `media/`, `staticfiles/` or `.venv/`
(they are git-ignored).

### Git deploys: `.cpanel.yml`

The repo contains a **`.cpanel.yml`** file. Once your repo is set up under
**Git Version Control**, use its **"Deploy HEAD Commit"** button and cPanel
will automatically run the deploy tasks for you: install dependencies, run
`migrate`, run `collectstatic`, and restart the app.

Open `.cpanel.yml` first and set `APP_NAME`/`PY_VER` (and `APP_ROOT` if your
repo is not cloned straight into `~/sboi`) to match your account. If you are
deploying by hand (File Manager), ignore this file and follow steps 3–7 below.

## 3. Create the Python application

1. cPanel → **Setup Python App** → **Create Application**.
2. Fill in:
   - **Python version:** 3.11 or newer (3.13 preferred).
   - **Application root:** `sboi` (the folder from step 2).
   - **Application URL:** your domain (e.g. `shekinahblaze.org`).
   - **Application startup file:** `passenger_wsgi.py`
   - **Application Entry point:** `application`
3. Click **Create**. cPanel makes a virtualenv (note its path, shown in the
   panel, e.g. `/home/myacct/virtualenv/sboi/3.13`).

## 4. Install dependencies

Open the app's **"Enter to the virtual environment"** command at the top of the
Python App page, run it in a Terminal/SSH session, then:

```bash
pip install --upgrade pip
pip install -r ~/sboi/requirements.txt
```

> If you truly have **no** terminal, some hosts expose a "Run pip install"
> field on the Python App page — enter `-r /home/myacct/sboi/requirements.txt`
> there. Otherwise contact your host to enable SSH for one command.

## 5. Configure environment variables

In the project root (`/home/myacct/sboi`) create a file named `.env` by copying
`.env.example` and filling it in:

```bash
cp ~/sboi/.env.example ~/sboi/.env
```

Edit it (File Manager → Edit) and set at least:

| Variable | Value |
| --- | --- |
| `SECRET_KEY` | long random string (see `.env.example` for the command) |
| `DB_NAME` | `myacct_sboi` |
| `DB_USER` | `myacct_sboiuser` |
| `DB_PASSWORD` | the database user's password |
| `ALLOWED_HOSTS` | `shekinahblaze.org,www.shekinahblaze.org` |
| `CSRF_TRUSTED_ORIGINS` | `https://shekinahblaze.org,https://www.shekinahblaze.org` |
| `ADMIN_URL` | your own secret path, e.g. `blaze-admin-9x2k` |

## 6. First-run setup (once)

Run these with the production settings. Use whichever "run a command" method
your host provides (Terminal, "Run Python script", or a temporary cron job like
the one described for `superuser.py`):

```bash
export DJANGO_SETTINGS_MODULE=sboi.settings_prod

python manage.py migrate
python manage.py collectstatic --noinput
```

`collectstatic` writes CSS/JS/images into `public_html/static`, and uploads are
stored in `public_html/media`.

### Create the admin without a terminal

cPanel has no interactive shell, so `createsuperuser` cannot prompt. Instead
use the `superuser.py` script.

It already contains default credentials, so you can run it as-is:

| Field | Default |
| --- | --- |
| Username | *(see `.env`)* |
| Email | `admin@shekinahblaze.org` |
| Password | *(see `.env`)* |

To use different values, set `SUPERUSER_USERNAME`, `SUPERUSER_EMAIL` and
`SUPERUSER_PASSWORD` in `.env` (they override the defaults).

1. cPanel → **Cron Jobs** → add a one-off job:

   ```
   /home/myacct/virtualenv/sboi/3.13/bin/python /home/myacct/sboi/superuser.py
   ```

2. Click **Run Now**, confirm the output ("Superuser ... created"), then
   **delete the cron job**.

The script is idempotent — re-running it when the user exists changes nothing.

> **Change this password after your first sign-in** (Admin → Users), since the
> default lives in a committed file.

### (Optional) Import existing content

```bash
# Locally:
python manage.py dumpdata --natural-foreign --natural-primary \
  -e contenttypes -e auth.Permission -e sessions -o data.json

# On cPanel: upload data.json to the project root, then run:
python manage.py loaddata data.json
```

## 7. Restart and verify

1. cPanel → **Setup Python App** → **Restart** the application.
2. Visit `https://shekinahblaze.org` — it must load over HTTPS with styles
   applied.
3. Sign in at `https://shekinahblaze.org/<your-ADMIN_URL>/`.
4. Run the deploy check (Terminal / temporary cron):

   ```bash
   python manage.py check --deploy
   ```

## 8. How files are served

| URL | Served from | By |
| --- | --- | --- |
| `/static/...` | `public_html/static` | Apache (after `collectstatic`) |
| `/media/...` | `public_html/media` | Apache (uploaded files) |
| everything else | the Django app | Passenger → `passenger_wsgi.py` |

Because these live inside `public_html`, Apache returns them directly — fast and
without waking Django. `MEDIA_ROOT`/`STATIC_ROOT` already point there via
`PUBLIC_HTML` in `sboi/settings_prod.py`.

## 9. Day-to-day

- **Redeploys:** pull the new code, then `pip install -r requirements.txt`,
  `python manage.py migrate`, `python manage.py collectstatic --noinput`, and
  **Restart** the app.
- **Backups:** cPanel → **phpMyAdmin** → the database → **Export** (or use the
  **Backup Wizard**).
- **Logs:** cPanel → **Setup Python App** (stderr log) and the domain's error
  log.
- **Bugs:** temporary cron running `python manage.py` commands as above.

## Security notes

- `SECRET_KEY`, the DB password and `ADMIN_URL` live only in `.env` (git-ignored).
- Cookies are HTTPS-only and SameSite=Lax; HSTS is on for a year.
- The admin URL is unguessable by design (no `/admin/` to brute-force).
- Delete one-off cron jobs (especially `superuser.py`) after you use them.

## Notes / troubleshooting

- **`ImproperlyConfigured: DB_NAME is not set`** — `.env` is missing or the
  variable is blank; check the file lives in the project root.
- **Redirect loop / not staying on HTTPS** — set `SECURE_SSL_REDIRECT=false`
  in `.env`.
- **`mysql_native_password` / driver errors** — this project uses PyMySQL, so no
  compiler is needed. If your MariaDB uses the `caching_sha2_password` plugin,
  `pip install cryptography` into the virtualenv.
- **Static files 404** — re-run `collectstatic` and confirm
  `public_html/static` exists; verify `STATIC_ROOT` in `sboi/settings_prod.py`.
