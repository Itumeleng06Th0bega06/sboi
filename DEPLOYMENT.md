# Deploying Shekinah Blaze to Render.com

Production domain: **shekinahblaze.org** · Settings module: `sboi.settings_prod`

## 1. What you need before starting

- A GitHub account (Render deploys from GitHub)
- A Render account (https://render.com)
- A `SECRET_KEY`: run
  `python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"`

> **Media (testing phase):** uploaded files currently live on Render's local
> disk. That disk is **ephemeral** — uploads are lost on every deploy/restart —
> and media is **not served** in production. Do not upload pictures from the
> admin during testing. Before going live with real uploads, add an
> S3-compatible bucket (Backblaze B2 / Cloudflare R2) and set the default
> storage to `storages.backends.s3boto3.S3Boto3Storage` in `settings_prod.py`.

## 2. Push the code to GitHub

The repo has no commits yet. `.gitignore` already excludes `db.sqlite3`, `media/`, `.venv/` and secrets — verify with `git status` before the first commit that nothing sensitive is staged.

```powershell
git add .
git commit -m "Initial commit: production-ready SBOI site"
git remote add origin https://github.com/<you>/sboi.git
git push -u origin main
```

## 3. Create the database (Render Postgres)

1. Render dashboard → **New → PostgreSQL**
2. Pick the smallest paid instance (this site is light)
3. After creation, open the database → **Connections** → copy the **Internal Database URL** → this is `DATABASE_URL`

## 4. Create the Web Service

1. Render dashboard → **New → Web Service** → connect your GitHub repo
2. Settings:
   - **Name:** `sboi`
   - **Region:** any (Frankfurt/Singapore/Virginia — pick closest to South Africa)
   - **Runtime:** Python 3 (Render reads `runtime.txt`)
   - **Build Command:**
     ```
     pip install -r requirements.txt && python manage.py collectstatic --noinput
     ```
   - **Start Command:**
     ```
     gunicorn sboi.wsgi:application --workers 2 --timeout 120 --graceful-timeout 60
     ```
   - **Health Check Path:** `/`
3. **Environment** (Advanced tab) — set every variable from `.env.example`:
   - `SECRET_KEY` (step 1)
   - `DATABASE_URL` (step 3)
   - `ALLOWED_HOSTS=shekinahblaze.org,www.shekinahblaze.org,.onrender.com`
   - `CSRF_TRUSTED_ORIGINS=https://shekinahblaze.org,https://www.shekinahblaze.org,https://*.onrender.com`
   - `ADMIN_URL=shekinah-fire-9x2k` — pick your own secret value, keep it private
4. **Create Web Service** → wait for the first deploy to finish.

## 5. First-run setup (one time)

On the web service → **Shell** tab, run:

```bash
python manage.py migrate --settings=sboi.settings_prod
python manage.py createsuperuser --settings=sboi.settings_prod
```

Import your existing database content (members, contact messages, site content):

```bash
# Locally, in the project folder:
python manage.py dumpdata --natural-foreign --natural-primary -e contenttypes -e auth.Permission -e sessions -o data.json

# In Render's Shell tab (upload data.json first via the Files tab):
python manage.py loaddata --settings=sboi.settings_prod data.json
```

> No media upload step for now — media is on the ephemeral disk during testing.

## 6. Point shekinahblaze.org at Render

1. Web Service → **Settings → Custom Domains** → add `shekinahblaze.org` and `www.shekinahblaze.org`
2. Render shows the DNS records — add them at your DNS provider (CNAME to the `onrender.com` hostname, plus the `_acme-challenge` TXT record)
3. Render provisions the Let's Encrypt certificate automatically

## 7. Verify it's secure

- Open `https://shekinahblaze.org` — the URL must never serve plain `http://`
- The admin lives only at `https://shekinahblaze.org/<your-secret-ADMIN_URL>/`
- Run `python manage.py check --deploy --settings=sboi.settings_prod` — it should report no issues

## 8. Day-to-day

- **Redeploys:** push to GitHub → Render rebuilds. The database is untouched.
- **Backups:** Render Postgres → **Backups** tab → take a manual backup before big changes.
- **Logs:** Web Service → **Logs** tab.
- **Bugs:** `python manage.py shell` in the Shell tab to inspect data.

## Security notes

- `SECRET_KEY`, `DATABASE_URL` and `ADMIN_URL` are **never** committed to git
- All cookies are HTTPS-only and SameSite=Lax; HSTS is on for a year
- The admin URL is unguessable by design (no `/admin/` to brute-force)
