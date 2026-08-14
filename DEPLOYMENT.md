# Deploying Shekinah Blaze to Render.com

Production domain: **shekinahblaze.org** · Settings module: `sboi.settings_prod`

## 1. What you need before starting

- A GitHub account (Render deploys from GitHub)
- A Render account (https://render.com)
- A **Backblaze B2** or **Cloudflare R2** account (free 10 GB tier — the site needs ~70 MB)
- A `SECRET_KEY`: run
  `python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"`

## 2. Push the code to GitHub

The repo has no commits yet. `.gitignore` already excludes `db.sqlite3`, `media/`, `.venv/` and secrets — verify with `git status` before the first commit that nothing sensitive is staged.

```powershell
git add .
git commit -m "Initial commit: production-ready SBOI site"
git remote add origin https://github.com/<you>/sboi.git
git push -u origin main
```

## 3. Create the media bucket (Backblaze B2)

1. Sign in to https://secure.backblaze.com/b2_buckets.htm
2. **Create a Bucket** → name `sboi-media` → set to **Public** (files are read directly by visitors)
3. Bucket details → copy the **Endpoint** (e.g. `https://s3.us-west-004.backblazeb2.com`) — this is `AWS_S3_ENDPOINT_URL`
4. **Application Keys** → Add a New Application Key with access to only this bucket → copy the **keyID** (`AWS_ACCESS_KEY_ID`) and **applicationKey** (`AWS_SECRET_ACCESS_KEY`)

> Using Cloudflare R2 instead? Bucket Settings → **Public Access** → enable and copy the `r2.dev` URL (or attach a custom domain) for `AWS_S3_CUSTOM_DOMAIN`. Endpoint: `https://<ACCOUNT_ID>.r2.cloudflarestorage.com`.

## 4. Create the database (Render Postgres)

1. Render dashboard → **New → PostgreSQL**
2. Pick the smallest paid instance (this site is light)
3. After creation, open the database → **Connections** → copy the **Internal Database URL** → this is `DATABASE_URL`

## 5. Create the Web Service

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
   - `DATABASE_URL` (step 4)
   - `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_STORAGE_BUCKET_NAME`, `AWS_S3_REGION_NAME`, `AWS_S3_ENDPOINT_URL` (step 3)
   - `ALLOWED_HOSTS=shekinahblaze.org,www.shekinahblaze.org,.onrender.com`
   - `CSRF_TRUSTED_ORIGINS=https://shekinahblaze.org,https://www.shekinahblaze.org,https://*.onrender.com`
   - `ADMIN_URL=shekinah-fire-9x2k` — pick your own secret value, keep it private
4. **Create Web Service** → wait for the first deploy to finish.

## 6. First-run setup (one time)

On the web service → **Shell** tab, run:

```bash
python manage.py migrate --settings=sboi.settings_prod
python manage.py createsuperuser --settings=sboi.settings_prod
```

Then upload your 70 MB of existing media into the bucket, preserving the folder structure
(`devotions/`, `gallery/`, `events/`, `materials/`, `about/`, `home/`, `slider/`, `sermons/`,
`announcements/`). Two easy ways:

- **B2 CLI:** `b2 file upload --folder media sboi-media .` (run from the project folder)
- **rclone:** `rclone sync media :b2:sboi-media`

Finally, import your existing database content (members, contact messages, site content):

```bash
# Locally, in the project folder:
python manage.py dumpdata --natural-foreign --natural-primary -e contenttypes -e auth.Permission -e sessions -o data.json

# In Render's Shell tab (upload data.json first via the Files tab):
python manage.py loaddata --settings=sboi.settings_prod data.json
```

## 7. Point shekinahblaze.org at Render

1. Web Service → **Settings → Custom Domains** → add `shekinahblaze.org` and `www.shekinahblaze.org`
2. Render shows the DNS records — add them at your DNS provider (CNAME to the `onrender.com` hostname, plus the `_acme-challenge` TXT record)
3. Render provisions the Let's Encrypt certificate automatically

## 8. Verify it's secure

- Open `https://shekinahblaze.org` — the URL must never serve plain `http://`
- The admin lives only at `https://shekinahblaze.org/<your-secret-ADMIN_URL>/`
- Run `python manage.py check --deploy --settings=sboi.settings_prod` — it should report no issues
- Upload a test image in the admin → it should appear in the B2 bucket, not on the server

## 9. Day-to-day

- **Redeploys:** push to GitHub → Render rebuilds. Database and media are untouched.
- **Backups:** Render Postgres → **Backups** tab → take a manual backup before big changes.
- **Logs:** Web Service → **Logs** tab.
- **Bugs:** `python manage.py shell` in the Shell tab to inspect data.

## Security notes

- `SECRET_KEY`, `DATABASE_URL`, `ADMIN_URL` and bucket keys are **never** committed to git
- All cookies are HTTPS-only and SameSite=Lax; HSTS is on for a year
- The admin URL is unguessable by design (no `/admin/` to brute-force)
- B2/R2 keys are scoped to the media bucket only
