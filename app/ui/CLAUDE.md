# Django UI — Claude Instructions

Django UI wrapping the T12 mapping pipeline. Page-isolated architecture
designed so each page can be worked on (by humans or AI) without reading
the rest of the codebase. Mirrors the file-based contract pattern the
`app/t12_pipeline/` stages use.

---

## How to Run

```bash
# From app/ui/
python manage.py migrate         # create DB tables (once, or after model changes)
python manage.py runserver       # dev server on http://127.0.0.1:8000
python manage.py check           # validate config without starting server

# Shell access (e.g. inspect Upload records)
python manage.py shell
```

---

## Architecture

```text
app/ui/
├── manage.py
├── db.sqlite3                       ← gitignored (dev only; prod = real DB)
├── storage/                         ← gitignored. MEDIA_ROOT in dev, S3 in prod.
│   └── <upload_id>/
│       ├── original/<file>.xlsx     ← saved by Upload.file (FileField)
│       └── pipeline/                ← file contract between pages
│           ├── block_detection.json
│           ├── annotated_blocks.json   ← rewritten by noi_verification on Recompute
│           ├── actual_noi.json
│           ├── computed_noi.json
│           ├── comparison.json        ← rewritten by noi_verification on Recompute
│           └── reviewed_data.json     ← data_review writes (future)
│
├── config/                          ← Django project (settings, root urls, wsgi/asgi)
│   ├── settings.py                  ← INSTALLED_APPS, MEDIA_ROOT, template auto-discovery
│   └── urls.py                      ← root: includes landing + t12_mapping
│
├── shared/                          ← cross-app utilities (NOT a Django app)
│   └── storage.py                   ← read_json / write_json / exists / get_local_path
│
├── templates/base.html              ← site-wide layout only
├── static/css/main.css
│
├── landing/                         ← Django app: workflow selector (home page)
│   ├── views.py, urls.py
│   └── templates/landing/index.html ← T12 + SWOT cards
│
└── t12_mapping/                     ← Django app: T12 workflow
    ├── models.py                    ← Upload model (lifecycle metadata)
    ├── migrations/                  ← Django migrations
    ├── pipeline_bridge.py           ← T12 pipeline interface (takes upload_id)
    ├── urls.py                      ← aggregates each page's urls
    └── pages/
        ├── upload/                  ← page = self-contained folder
        │   ├── views.py
        │   ├── urls.py
        │   ├── README.md            ← feature spec (reads/writes/URL/next)
        │   └── templates/upload/upload.html
        ├── noi_verification/
        │   ├── views.py
        │   ├── helpers.py           ← page-local helpers
        │   ├── urls.py
        │   ├── README.md
        │   └── templates/noi_verification/verify.html
        ├── data_review/             ← FUTURE
        └── analytics/               ← FUTURE
```

---

## Three Layers

| Layer | Where | What it does |
|---|---|---|
| **Storage abstraction** | `shared/storage.py` | All JSON I/O between pages. Backed by Django's `default_storage` so dev=local FS and prod=S3 differ by one settings line. |
| **Persistence model** | `t12_mapping/models.py` (`Upload`) | Tracks every upload's lifecycle: id (UUID), file (FileField), status, current_step, user FK, timestamps. Source of truth for "which uploads exist". |
| **Pages** | `t12_mapping/pages/<name>/` | Self-contained view + helpers + templates. Pages never import each other; they share data only via storage (files) and DB (Upload). |

### Storage Abstraction

Public API in `shared/storage.py`:

```python
storage.read_json(upload_id, "comparison.json")       # → dict
storage.write_json(upload_id, "annotated.json", data) # overwrites if present
storage.exists(upload_id, "corrections.json")         # → bool
storage.get_local_path(file_field)                    # for libs needing a real path (openpyxl)
```

Files land at `MEDIA_ROOT/<upload_id>/pipeline/<filename>` in dev. The
`default_storage` indirection means swapping to S3 in prod is one settings
line — pages and pipeline_bridge don't change.

### Upload Model

```python
Upload(
    id            = UUID (primary key, auto)
    file          = FileField(upload_to=<upload_id>/original/)
    file_name     = str
    property_name = str
    status        = "draft" | "complete"        # lifecycle
    current_step  = "upload" | "noi_verification" | "data_review" | "analytics"
    created_at    = auto_now_add
    updated_at    = auto_now
    user          = FK(auth.User, nullable)     # auth comes later
)
```

Why it matters:
- "Which uploads exist?" → `Upload.objects.all()`
- "Per-user filtering" later → `Upload.objects.filter(user=request.user)`
- "Cleanup old drafts" → `Upload.objects.filter(status="draft", created_at__lt=cutoff).delete()` (cascades file deletion via FileField)
- "Resume mid-flow" → check `upload.current_step` to know where to redirect

---

## Page Contract Convention

Each page is one folder under `t12_mapping/pages/`. The folder contains:

```text
pages/<page>/
├── __init__.py
├── views.py                         ← one view function (or a few closely related)
├── urls.py                          ← urlpatterns for this page
├── helpers.py                       ← page-local helpers (optional)
├── README.md                        ← feature spec (REQUIRED)
└── templates/<page>/<page>.html     ← template (auto-discovered by settings)
```

Each page's `README.md` declares its contract:

```markdown
URL:    /t12/<upload_id>/<route>/
Reads:  <files this page reads from storage>
Writes: <files this page writes to storage>
DB:     <Upload field changes this page makes>
Next:   <which page it redirects to>
```

**Rules:**
- Pages **never** import each other (no `from t12_mapping.pages.upload import ...` inside `noi_verification`)
- Pages communicate **only** via:
  1. Files in `storage/<upload_id>/pipeline/` (via `shared.storage`)
  2. The `Upload` DB row (status, current_step)
  3. URL parameters (`upload_id`)
- If a page changes what it reads/writes, **update its README**. The downstream page's README is the canary for broken contracts.

---

## How to Add a New Page

Example: adding `data_review` page.

1. Create folder + files:
   ```bash
   mkdir -p t12_mapping/pages/data_review/templates/data_review
   touch t12_mapping/pages/data_review/__init__.py
   ```
2. Write `views.py` (read from storage, render template, write on POST):
   ```python
   from django.shortcuts import get_object_or_404, render
   from shared import storage
   from t12_mapping.models import Upload

   def review(request, upload_id):
       upload = get_object_or_404(Upload, pk=upload_id)
       data = storage.read_json(upload.id, "annotated_blocks.json")
       # ... build context, handle POST ...
       return render(request, "data_review/review.html", {"upload": upload, ...})
   ```
3. Write `urls.py`:
   ```python
   from django.urls import path
   from . import views
   urlpatterns = [path("<uuid:upload_id>/review/", views.review, name="data_review")]
   ```
4. Write `README.md` declaring reads/writes/URL/next.
5. Write `templates/data_review/review.html` (extends `base.html`).
6. Wire into `t12_mapping/urls.py`:
   ```python
   path("", include("t12_mapping.pages.data_review.urls")),
   ```
7. Done. Templates are auto-discovered; settings does not need editing.

---

## How to Add a New Workflow (e.g. SWOT)

1. Copy `t12_mapping/` shape to `swot_analysis/`. Rename references inside.
2. Add `swot_analysis` to `INSTALLED_APPS` and `WORKFLOW_APPS` in `config/settings.py`.
3. Add `path("swot/", include("swot_analysis.urls"))` to `config/urls.py`.
4. Flip the SWOT card in `landing/templates/landing/index.html` from disabled to active.
5. Build pages under `swot_analysis/pages/` using the same contract convention.

The SWOT workflow gets its own `models.py` (e.g. `SwotReport`), its own
`pipeline_bridge.py`, and its own pages. It does not share helpers with
T12. Independent workflows = independent code.

---

## Cloud Deployment Plan

Currently local-only. To deploy:

1. `pip install django-storages boto3`
2. In `config/settings.py` (prod env):
   ```python
   DEFAULT_FILE_STORAGE     = 'storages.backends.s3boto3.S3Boto3Storage'
   AWS_STORAGE_BUCKET_NAME  = '...'
   AWS_S3_REGION_NAME       = '...'
   ```
3. Swap `DATABASES` to PostgreSQL.
4. (One thing to handle): `storage.get_local_path()` uses `default_storage.path()` which raises on S3. For S3, that function must download the file to a temp path. Update `shared/storage.py` when this comes up.

Pages and `pipeline_bridge.py` do not change. `Upload` records (and their `file` FileField) automatically use whatever storage backend is configured.

---

## Coding Rules

- **No `Path()` / `open()` for cross-page state.** Use `shared.storage` exclusively.
- **No raw filesystem paths in views.** Use `Upload.file` (FileField) for the original upload; use `storage.*` for generated JSON.
- **One view per page** unless multiple URLs genuinely share state. If a page needs multiple endpoints, they all live in the same `pages/<name>/views.py`.
- **Page-local helpers stay page-local.** A helper used by only one page goes in `pages/<name>/helpers.py`, not in `shared/`.
- **`shared/` is for things used by 2+ workflow apps.** Don't put T12-only code there.
- **Templates use page-local paths.** `noi_verification/verify.html`, not `t12_mapping/noi_verification.html`. The auto-discovery in `settings.py` makes this work.
- **READMEs are required.** Every page folder has a `README.md` declaring its contract. Update it when you change reads/writes.
- **Use `get_object_or_404(Upload, pk=upload_id)`** in every page view that takes an `upload_id`. Don't manually check existence.
- **Fail hard on missing pipeline files.** If a page expects `comparison.json` and it's not there, raise `FileNotFoundError` — don't render with empty data.
- **Persist on every state-changing POST.** Don't keep corrections in memory only; refresh should show the latest state.

---

## What Not To Do

- Do not import `pages/<a>` from `pages/<b>` — pages are isolated.
- Do not put cross-cutting logic in `t12_mapping/views.py` — that file no longer exists by design. Pages own their own views.
- Do not use raw `open()` or `Path()` for JSON between pages — always go through `shared.storage`.
- Do not skip the README when adding a page — it's the contract.
- Do not put T12-only helpers in `shared/` — that folder is reserved for cross-workflow utilities.
- Do not edit `templates/` (the top-level one) for page-specific HTML — only `base.html` lives there. Page templates live inside the page folder.
- Do not manually create folders under `storage/` — `Upload.objects.create(file=...)` + `storage.write_json(...)` create them as needed.
- Do not bypass the `Upload` model — never reference a `storage/<uuid>/` directory that has no DB row. The DB row IS the source of truth for "is this upload real."
- Do not add `pages/<name>/templates/` to `TEMPLATES['DIRS']` manually — the auto-discovery in `settings.py` handles it.
