# Contributing to GreenLead

Thanks for taking the time to look at the code.

> **Licensing note:** this project is published under an **All Rights Reserved**
> licence (see [LICENSE](LICENSE)). Contributions are welcome, but by opening a
> pull request you agree that copyright in your contribution is assigned to the
> project's copyright holder.

---

## Getting set up

```bash
python -m venv .venv
# Windows:  .\.venv\Scripts\Activate.ps1     |  Unix:  source .venv/bin/activate

pip install -e ".[dev]"
cp .env.example .env          # never commit .env

alembic upgrade head          # build the schema
python scripts/seed_demo.py   # optional: demo data + demo logins
uvicorn greenlead.main:app --reload
```

## Before you open a pull request

Run the same three checks CI runs — if these pass locally, CI will pass:

```bash
ruff check . && ruff format --check .
mypy src
pytest -q --cov=greenlead --cov-fail-under=80
```

CI additionally verifies that Alembic can build the database from empty and
tear it back down (`alembic upgrade head` → `alembic downgrade base`).

## Architectural rules

These are the conventions that keep the codebase predictable. A PR that breaks
one of them will be asked to change, even if the tests pass.

1. **Routes stay thin.** No SQL, no business rules, and no permission decisions
   in `api/routes/` or in templates. A route validates input, calls one service
   method, and renders.
2. **Authorization lives in exactly one place** — `core/policy.py`. Services
   expose `*_for(actor, …)` methods, and routes call *only* those. Never
   re-implement a permission check at the route or template layer.
3. **Storage is swappable.** Business logic talks to the repository contracts in
   `repositories/base.py`, never to SQLAlchemy directly. Anything you add must
   work against the in-memory adapter as well as the SQL one.
4. **Audit ≠ analytics.** "Who changed what" (security) and "how is the product
   used" (product events) are separate stores. Keep them separate.
5. **Never log or store secrets.** The audit layer redacts passwords, tokens and
   API keys — don't route around it.
6. **The schema is owned by Alembic.** Any model change needs a migration;
   `create_all` is dev-only and must never be relied on in production.
7. **Both languages, always.** User-facing strings go through the translation
   tables in `core/i18n.py` — Arabic (RTL) and English (LTR) stay at parity.
8. **Nothing organization-specific in code.** Company names, industries and
   similar labels belong in configuration — see
   [docs/CUSTOMIZATION.md](docs/CUSTOMIZATION.md).

## Tests

- Every behavioural change needs a test. Coverage must stay at or above **80%**.
- Authorization changes need an explicit **IDOR test**: for an actor without
  access, a record that exists and a record that does not must be
  indistinguishable (both `404`).
- Keep tests deterministic — inject `today=` into date-sensitive services rather
  than depending on the real clock.

## Commit messages

This repo follows Conventional Commits:

```
feat(meetings): add .ics export
fix(dashboard): correct overdue follow-up boundary
docs(readme): document demo accounts
test(ownership): pin the dashboard clock
refactor(repositories): extract session factory
chore(ci): add Python 3.12 to the matrix
```

Keep the subject in the imperative mood and under ~72 characters.

## Reporting a security issue

Please **do not** open a public issue for a security vulnerability. See
[docs/SECURITY.md](docs/SECURITY.md).
