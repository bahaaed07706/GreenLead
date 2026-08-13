# Customization Guide

GreenLead ships **white-label**. Nothing about a specific company, industry or
market is baked into the code — the identity is configuration. This guide shows
how to adapt the platform to your own organization, role or interests.

Work through it in order: **§1 costs you two minutes**, §2–§3 are cosmetic, and
§4 onward is for when you want to extend the data model itself.

---

## 1. Rebrand it (no code)

Copy the example environment file and edit the branding block:

```bash
cp .env.example .env
```

```bash
APP_NAME=Acme Pipeline                    # product name shown in the browser tab
ORG_NAME=Acme Corp                        # your organization's name
ORG_INDUSTRY=Manufacturing                # default sector + research keyword
APP_DESCRIPTION=Our sales operating system  # shown in the API docs
```

Restart the server — that's it.

### What each variable actually controls

| Variable | Where it appears | Default |
|---|---|---|
| `APP_NAME` | Browser tab title, FastAPI docs title, startup log | `GreenLead` |
| `ORG_NAME` | Available to every template as `{{ org_name }}` | `Your Company` |
| `ORG_INDUSTRY` | Sector placeholder on the new-company form, the fallback sector badge on the dashboard, and the industry keyword in the research query | `Technology` |
| `APP_DESCRIPTION` | The description in the OpenAPI schema at `/docs` | `Business-development & sales-intelligence platform` |

These are **labels and defaults only** — no business rule, permission check or
migration depends on them, so changing them is always safe.

### Using them in your own templates

`org_name` and `org_industry` are injected into every template context by
`get_lang_context()` in `src/greenlead/core/i18n.py`:

```jinja
<h1>{{ org_name }} — Pipeline</h1>
<span class="badge">{{ company.sector or org_industry }}</span>
```

To add another branding variable, follow the same three steps:

1. Add the field to `Settings` in `src/greenlead/core/config.py`
2. Add it to the returned dict in `get_lang_context()`
3. Add it to `.env.example` so the next person knows it exists

---

## 2. Change the visual identity

**Logo** — replace `static/images/logo.svg` with your own (keep the filename, or
update the `<img>` in `templates/_sidebar.html`).

**Product name in the sidebar** — `templates/_sidebar.html` lines 6–7 hold the
wordmark and tagline:

```jinja
<div class="brand-name">Green<span>Lead</span></div>
<div class="brand-tag">Sales Intelligence</div>
```

Swap them for your own, or make them dynamic with `{{ org_name }}`.

**Colours** — every colour is a CSS custom property at the top of
`static/css/style.css`. Change these and the whole UI follows:

```css
--primary: #1B7458;        /* buttons, links, active states */
--primary-hover: #145E47;
--sidebar: #12352D;        /* sidebar background */
--canvas: #F4F7F6;         /* page background */
```

Don't hardcode colours in templates — always use `var(--primary)` and friends so
the palette stays swappable.

---

## 3. Change the wording (and the languages)

All user-facing strings live in the `TRANSLATIONS` dictionary in
`src/greenlead/core/i18n.py`, with an `en` and an `ar` block.

```python
TRANSLATIONS = {
    "en": {"companies_title": "Companies", ...},
    "ar": {"companies_title": "الشركات", ...},
}
```

To rename something — "Companies" → "Accounts", say — edit both blocks and use
`{{ t.companies_title }}` in templates. **Keep the two languages at parity:**
every key must exist in both, or the other language will fall back to a missing
value.

To add a third language, add a new block with the same keys. Right-to-left
languages should follow the `dir` handling already applied to Arabic.

---

## 4. Add your own field to a record

Say you want a **`budget`** field on companies. There are four layers, in order:

**1. Domain schema** — `src/greenlead/models/schemas.py`

```python
class CompanyBase(BaseModel):
    ...
    budget: str | None = None
```

**2. Database model** — `src/greenlead/repositories/sql_models.py`

```python
budget: Mapped[str | None] = mapped_column(String, nullable=True)
```

**3. Migration** — never edit the database by hand:

```bash
alembic revision --autogenerate -m "add company budget"
alembic upgrade head
```

Open the generated file in `migrations/versions/` and check it before running —
autogenerate is a starting point, not an oracle.

**4. Templates** — add the input to `templates/companies/new.html` and display it
in `templates/companies/detail.html`.

The in-memory repository (`repositories/memory.py`) works off the Pydantic
schema, so it picks the field up automatically — which is why the tests keep
passing without a database.

---

### Default timezone

Meetings default to the **`Asia/Riyadh`** IANA timezone. This is a functional
default, not branding — it is set in three places that must stay in agreement:

- `src/greenlead/models/schemas.py` (the `timezone` fields)
- `src/greenlead/repositories/sql_models.py` (the column default)
- a new Alembic migration, if you change the column default

Changing it affects stored data, so treat it as a schema change rather than a
cosmetic one. Existing records keep whatever timezone they were created with.

---

## 5. Swap the storage backend

Set `DATABASE_URL` in `.env`:

| Value | Backend |
|---|---|
| *(empty)* | In-memory — zero setup, data lost on restart. Good for a demo. |
| `sqlite:///./greenlead.db` | SQLite — survives restarts. Good for local use. |
| `postgresql+psycopg://user:pass@host:5432/greenlead` | PostgreSQL. Run `pip install -e ".[postgres]"` first. |

Run `alembic upgrade head` after pointing at a new database.

---

## 6. Turn on the optional integrations

All of these are inert until you supply credentials — the app runs fine without
them.

| Integration | Variables | Effect when unset |
|---|---|---|
| Web research | `TAVILY_API_KEY` | A deterministic mock provider is used |
| AI extraction | `AI_PROVIDER` + `OPENAI_API_KEY` / `GEMINI_API_KEY` | Mock extraction; status shown as not configured |
| Google Sheets | `GOOGLE_SHEET_ID`, `GOOGLE_SERVICE_ACCOUNT_FILE` | Sheets adapter disabled |

To plug in a different research or AI vendor, implement the `SearchProvider` or
`AIProvider` interface in `src/greenlead/providers/base.py` and register it —
`providers/mock.py` is the reference implementation, and `providers/tavily.py`
shows a real HTTP one.

---

## 7. Adjust roles and permissions

Roles are `employee`, `manager` and `admin`. The rules that map a role to what it
can see and do live in **one file**: `src/greenlead/core/policy.py`.

Change permissions there — never in a route or a template. Services expose
`*_for(actor, …)` methods that consult the policy, and every route calls only
those. Keeping this centralized is what makes the authorization testable.

If you add a rule, add an **IDOR test** alongside it: for an actor without
access, a record that exists and one that doesn't must be indistinguishable
(both `404`), so ids can't be enumerated.

---

## Security reminders when you deploy

- Generate a real `SECRET_KEY` — never ship the placeholder.
- Generate your own `ADMIN_PASSWORD_HASH`:
  ```bash
  python -c "from passlib.hash import bcrypt; print(bcrypt.hash('your-password'))"
  ```
- Set `APP_ENV=production`. This also makes `scripts/seed_demo.py` refuse to run,
  so the public demo accounts can never be created on a live deployment.
- Never commit `.env` — it is git-ignored, keep it that way.
