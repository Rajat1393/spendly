# Spec: Login and Logout

## Overview
This step wires up the login and logout flows. The `GET /login` route already renders the form and flash messages are already wired (Step 02); this step adds the `POST /login` handler that verifies credentials, creates a session on success, and redirects to the profile page. It also implements `GET /logout`, which currently returns a stub string, replacing it with a proper session clear and redirect. Together these two routes complete the full authentication round-trip that Step 04 (Profile) and all expense routes depend on.

## Depends on
- Step 01 — Database Setup (`get_db()`, `users` table must exist)
- Step 02 — Registration (`app.secret_key` set, `flash()` system in place, session available)

## Routes
- `POST /login` — verify email/password, create session, redirect to profile — public
- `GET /logout` — clear session, redirect to landing page — public (harmless if not logged in)

## Database changes
No new tables or columns. Add one helper to `database/db.py`:

- `get_user_by_email(email)` — fetches a single row from `users` WHERE email matches. Returns a `sqlite3.Row` (dict-like) or `None` if not found. Used by the login route to retrieve the stored `password_hash` for comparison.

## Templates
- **Modify:** `templates/base.html` — update the navbar so it shows context-aware links:
  - When `session` is empty (logged out): show existing "Sign in" and "Get started" links
  - When `session['user_id']` is set (logged in): show the user's name and a "Sign out" link that points to `url_for('logout')`
- **No other template changes needed** — `login.html` already has `method="POST"`, correct field `name` attributes, and flash message rendering from Step 02.

## Files to change
- `app.py` — add `POST /login` handler; replace the `GET /logout` stub; add `check_password_hash` import; add `session` to Flask imports
- `database/db.py` — add `get_user_by_email()` helper; add `get_user_by_email` to exports used by `app.py`
- `templates/base.html` — conditional navbar based on `session`

## Files to create
None.

## New dependencies
No new pip packages. Uses:
- `werkzeug.security.check_password_hash` (already in requirements)
- `flask.session` (already in Flask, `secret_key` already set in Step 02)

## Rules for implementation
- No SQLAlchemy or ORMs — raw `sqlite3` only
- Parameterised queries only — never f-strings in SQL
- Password verification with `werkzeug.security.check_password_hash` — never compare plain text
- Use CSS variables — never hardcode hex values in templates or stylesheets
- All templates extend `base.html`
- `session` stores only `user_id` (integer) and `user_name` (string) — nothing sensitive
- On invalid credentials: flash a deliberately vague error (`"Invalid email or password."`) — do not reveal which field was wrong
- On successful login: `session['user_id'] = user['id']`, `session['user_name'] = user['name']`, then `redirect(url_for('profile'))`
- `GET /logout`: call `session.clear()`, then `redirect(url_for('landing'))` — no flash needed
- `get_user_by_email()` lives in `database/db.py`, not inline in the route
- Validate email and password fields are non-empty before hitting the DB; flash the same vague error if either is blank (prevents user enumeration)

## Definition of done
- [ ] Submitting the login form with a valid email and correct password creates a session and redirects to `/profile`
- [ ] Submitting with a wrong password shows `"Invalid email or password."` — form re-renders, no redirect
- [ ] Submitting with an unregistered email shows the same vague error — no 500
- [ ] Submitting with any blank field shows the same vague error — no DB hit
- [ ] Visiting `/logout` clears the session and redirects to `/`
- [ ] Visiting `/logout` when already logged out redirects to `/` without error
- [ ] Navbar shows "Sign in" and "Get started" when logged out
- [ ] Navbar shows user's name and "Sign out" link when logged in
- [ ] `GET /login` still renders the empty form unchanged
- [ ] App starts without errors (`python app.py`)
