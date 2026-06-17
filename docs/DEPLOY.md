# Deploying to Render

The app is configured to deploy to [Render](https://render.com) as a Django web service. This guide walks through the dashboard click-through, from "new account" to "live URL". Total time: **~15 minutes**.

## Prerequisites

- A GitHub account with access to this repo
- A Render account (free, sign up at https://render.com)
- An OpenAI API key (https://platform.openai.com/api-keys)

## What gets deployed

| Branch | `demo` |
|---|---|
| Root directory | `app/ui` (Django project lives here) |
| Build command | `./build.sh` (defined at repo root) |
| Start command | `gunicorn config.wsgi:application` (defined in `Procfile`) |
| Python | 3.11.10 (pinned in `runtime.txt`) |
| Database | SQLite on disk (default) — set `DATABASE_URL` env var to switch to Postgres |
| File storage | Local disk under `app/ui/storage/` — set `MEDIA_ROOT_PATH` to point at a Render persistent disk |

## Step-by-step

### 1. Connect Render to GitHub

1. Sign in at https://dashboard.render.com.
2. Click **New +** → **Web Service**.
3. **Connect a repository** — authorize Render to read your GitHub repos if prompted.
4. Pick this repo from the list (`real-estate-deal-analysis-ai-pipeline` or whatever it's called).

### 2. Configure the service

Fill in these fields:

| Field | Value |
|---|---|
| **Name** | `t12-mapping` (or anything; this becomes part of the public URL) |
| **Region** | Closest to your audience (e.g. Oregon for US-West) |
| **Branch** | `demo` |
| **Root Directory** | *(leave blank)* — the build script handles cd-ing into `app/ui` |
| **Runtime** | Python 3 |
| **Build Command** | `./build.sh` |
| **Start Command** | *(leave blank — `Procfile` provides it)* |
| **Plan** | **Free** to start. Upgrade to **Starter ($7/mo)** the day of the investor demo so there's no cold-start delay. |

### 3. Set environment variables

Scroll to **Environment Variables** and add these:

| Key | Value | Notes |
|---|---|---|
| `SECRET_KEY` | Click "Generate" — any random 50-char string | Django will use this to sign sessions, CSRF tokens, etc. |
| `DEBUG` | `False` | Production mode |
| `OPENAI_API_KEY` | Your OpenAI key (`sk-proj-...`) | Used by the AI mapping fallback |
| `OPENAI_API_KEY_AI_MAPPING` | Same value as `OPENAI_API_KEY` | Code reads this specific name for the mapping agent |
| `OPENAI_MODEL` | `gpt-4o-mini` | Recommended for demo (cheap, fast, plenty good) |
| `ALLOWED_HOSTS` | *Leave blank for now* | Render auto-injects `RENDER_EXTERNAL_HOSTNAME` after first deploy; the code uses that automatically |
| `PYTHON_VERSION` | `3.11.10` | Matches `runtime.txt` |

### 4. Click "Create Web Service"

Render starts building. First build takes **3–5 minutes** because it has to install Django + openpyxl + langchain. Watch the build logs in the dashboard.

**What you should see in the logs:**

```
==> Installing Python dependencies
==> Collecting static files (Django)
==> Applying database migrations
==> Build complete
==> Starting service with 'gunicorn config.wsgi:application ...'
==> Your service is live 🎉
```

### 5. Visit the live URL

Once the deploy completes, Render shows the URL at the top of the service page:

```
https://t12-mapping-xxxx.onrender.com
```

Open it. You should see the landing page with the T12 Mapping tile. Click in, upload a sample file, and verify the full flow.

---

## Cost expectations

| Tier | Monthly cost | Notes |
|---|---|---|
| Free | **$0** | Server sleeps after 15 min idle. First request after sleep takes ~60s. Fine for casual sharing. |
| Starter | **$7** | Always-on, instant responses. Worth upgrading for investor demos. Cancel after. |
| Render Postgres free | **$0** | Optional add-on. Database survives restarts. Auto-deletes after 90 days. |
| Render persistent disk | **$0.25/GB-month** | Optional. Lets uploaded T12 files survive restarts. Skip for demos unless you're pre-loading files. |

For OpenAI:

- `gpt-4o-mini`: ~$0.001–0.005 per upload. A handful of demos = under $1 total.
- Set a hard cap in your OpenAI dashboard (e.g. $20/month) so a demo gone wild doesn't surprise you.

---

## After deployment

### Auto-redeploy on push

Every push to `demo` triggers a redeploy automatically. So the workflow is:

```bash
# Make changes on a feature branch
git checkout -b feat/something-new
# ... commit ...
git checkout main
git merge feat/something-new
git checkout demo
git merge main          # fast-forward; Render rebuilds + redeploys
git push origin demo
```

### Roll back a bad deploy

Render keeps the previous deploy. From the dashboard: **Service** → **Deploys** → click an earlier deploy → **Redeploy**. Or revert the commit on the `demo` branch and push.

### Switch to Postgres later

1. From the Render dashboard, click **New +** → **PostgreSQL**.
2. Pick Free plan (90-day trial). Region: same as your web service.
3. Once created, copy the **Internal Database URL**.
4. In your web service's Environment, add `DATABASE_URL` = (paste the URL).
5. Render auto-redeploys; Django's `dj-database-url` picks it up.

### Add persistent disk for uploads

1. From the web service page, **Settings** → **Disks** → **Add Disk**.
2. Mount Path: `/var/data`. Size: 1 GB (free).
3. In Environment, add `MEDIA_ROOT_PATH` = `/var/data`.
4. Redeploy.

---

## Troubleshooting

| Symptom | Likely cause |
|---|---|
| `DisallowedHost` error | `ALLOWED_HOSTS` not picking up the Render domain. Manually set it to `<your-app>.onrender.com`. |
| Static files 404 (no CSS) | `collectstatic` didn't run, or `STATIC_ROOT` missing. Check build logs for the collectstatic step. |
| `ModuleNotFoundError: t12_pipeline` | The editable install failed. Check requirements.txt has `-e ./app/t12_pipeline`. |
| AI mapping returns errors | `OPENAI_API_KEY_AI_MAPPING` not set, or wrong/expired key, or hit rate limits. Check OpenAI dashboard. |
| First request after a while hangs ~60s | Free tier spin-down. Normal. Upgrade to Starter for instant responses. |
| Uploaded file disappears next visit | Free tier ephemeral disk. Either upgrade to Starter + add disk, or use S3. Expected for demos. |
