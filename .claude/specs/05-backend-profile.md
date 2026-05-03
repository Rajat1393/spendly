# Spec: Backend Profile

## Overview
This step replaces all hardcoded data in the `/profile` route with real database queries. Step 04 built the full profile UI with static placeholder values; Step 05 wires it to the `users` and `expenses` tables so the page reflects the logged-in user's actual data — real name, email, member-since date, total spend, transaction count, top category, recent transactions, and per-category totals. No new routes or templates are needed; only `database/db.py` and the `/profile` view function in `app.py` change.

## Depends on
- Step 01 — Database Setup (`users` and `expenses` tables, `get_db()`)
- Step 02 — Registration (users exist in the DB)
- Step 03 — Login / Logout (`session['user_id']` is set on login)
- Step 04 — Profile Page (`profile.html` template is complete and expects the same context keys)

## Routes
No new routes.

## Database changes
No new tables or columns. Add the following helpers to `database/db.py`:

- `get_user_by_id(user_id)` — fetch a single row from `users` by primary key; returns `sqlite3.Row` or `None`.
- `get_recent_expenses(user_id, limit=5)` — return the `limit` most-recent expense rows for the user, ordered by `date DESC`, then `created_at DESC`.
- `get_expense_stats(user_id)` — return a dict with:
  - `total_spent` — `SUM(amount)` for the user (float, 0.0 if no rows)
  - `transaction_count` — `COUNT(*)` for the user (int)
- `get_category_totals(user_id)` — return a list of dicts `{name, total}` grouped by `category`, ordered by `total DESC`. Each `total` is the sum of `amount` for that category.
- `get_top_category(user_id)` — return the category name with the highest total spend, or `"—"` if no expenses exist.

## Templates
- **Modify:** `templates/profile.html` — no structural changes; verify that every context key the template references matches the new dict shapes passed from the route (see Files to change). Fix any key-name mismatches that arise.

## Files to change
- `database/db.py` — add the five new helper functions listed above.
- `app.py` — rewrite the `/profile` view body:
  1. Guard: if `session.get("user_id")` is falsy, `redirect(url_for("login"))`.
  2. Call `get_user_by_id(session["user_id"])`; if `None`, `session.clear()` and `redirect(url_for("login"))`.
  3. Compute `initials` from `user["name"]` (same logic as current stub).
  4. Format `member_since` from `user["created_at"]` (parse ISO datetime, format as e.g. `"January 2024"`).
  5. Call `get_expense_stats`, `get_top_category`, `get_recent_expenses`, `get_category_totals`.
  6. Build the same `user`, `stats`, `transactions`, and `categories` context dicts the template already expects — now populated from DB results.
  7. Compute a `percent` for each category row: `round(cat_total / total_spent * 100)` (guard against divide-by-zero when `total_spent == 0`).
  8. Format amounts for display as plain floats or Indian-locale strings — match whatever format `profile.html` already uses.

## Files to create
None.

## New dependencies
No new dependencies. Uses only `sqlite3` (stdlib) and `datetime` (stdlib).

## Rules for implementation
- No SQLAlchemy or ORMs — raw `sqlite3` via `get_db()` only
- Parameterised queries only — never f-strings or `.format()` in SQL
- Passwords hashed with werkzeug (no auth changes in this step)
- Use CSS variables — never hardcode hex values
- All templates extend `base.html`
- Every DB helper must open its own connection with `get_db()` and close it before returning
- `total_spent` defaults to `0.0` when `SUM(amount)` returns `NULL` (no expenses) — use `COALESCE(SUM(amount), 0)`
- Percent calculation must guard against `total_spent == 0` (return 0 for all categories)
- `get_user_by_id` returning `None` must be handled in the route — treat it as an invalid session

## Definition of done
- [ ] Visiting `/profile` while logged in shows the real user's name and email (not "priya@example.com")
- [ ] The member-since date reflects the user's actual `created_at` value from the DB
- [ ] Total spent and transaction count reflect real rows in the `expenses` table
- [ ] Top category reflects the category with the highest real spend (or `"—"` if no expenses)
- [ ] Transaction history shows the 5 most-recent real expenses for the logged-in user
- [ ] Category breakdown shows real per-category totals and percentages
- [ ] Seeding a second user and logging in as them shows only their own data
- [ ] Visiting `/profile` with no session redirects to `/login`
- [ ] If `session['user_id']` points to a deleted/non-existent user, session is cleared and user is redirected to `/login` without a 500
- [ ] App starts without errors (`python app.py`)
- [ ] All new DB helpers use parameterised queries (verify by inspection — no f-strings in SQL)
