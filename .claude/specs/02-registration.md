# Spec: Registration

## Overview
This step wires up the registration form so new users can create an account. The `GET /register` route already renders the form; this step adds the `POST /register` handler that validates the submission, hashes the password, inserts the user, and redirects on success. It also introduces Flask sessions and flash messaging, which every subsequent authenticated step depends on.

## Depends on
- Step 01 — Database Setup (`get_db()`, `init_db()`, `users` table must exist)

## Routes
- `POST /register` — process registration form, create user, redirect to login — public

## Database changes
No new tables or columns. Add one helper to `database/db.py`:

- `create_user(name, email, password_hash)` — inserts a row into `users`, returns the new `id`. Raises `sqlite3.IntegrityError` if the email is already taken (UNIQUE constraint).

## Templates
- **Modify:** `templates/register.html` — add `method="POST"` to the form, wire `name` attributes on all inputs, render flash messages (errors and success) above the form.
- **Modify:** `templates/base.html` — add a flash message block so all pages can display messages (needed by login and later steps too).

## Files to change
- `app.py` — add `POST /register` route; set `app.secret_key`; import `create_user` and `flash`, `redirect`, `request`, `url_for`, `session`
- `database/db.py` — add `create_user()` helper
- `templates/register.html` — wire form, show flash messages
- `templates/base.html` — add flash message rendering block

## Files to create
None.

## New dependencies
No new pip packages. Uses:
- `werkzeug.security.generate_password_hash` (already in requirements)
- `flask.flash`, `flask.session`, `flask.redirect`, `flask.request` (already in Flask)

## Rules for implementation
- No SQLAlchemy or ORMs — raw `sqlite3` only
- Parameterised queries only — never f-strings in SQL
- Passwords hashed with `werkzeug.security.generate_password_hash` before storing
- Use CSS variables — never hardcode hex values in templates or stylesheets
- All templates extend `base.html`
- `app.secret_key` must be set before any `flash()` or `session` usage; use `os.urandom(24)` or a fixed dev key — flag that it must be an env var in production
- `create_user()` lives in `database/db.py`, not in the route
- On duplicate email: catch `sqlite3.IntegrityError`, flash a user-friendly error, re-render the form (do not 500)
- On success: flash a success message and `redirect(url_for('login'))`
- Validate that name, email, and password fields are all non-empty before hitting the DB; flash an error if any are missing

## Definition of done
- [ ] Submitting the form with valid data creates a new row in `users` with a hashed password
- [ ] Submitting with an email that already exists shows an inline error message, does not crash
- [ ] Submitting with any empty field shows an inline error message
- [ ] Successful registration redirects to `/login`
- [ ] Flash messages appear on the page without breaking the existing layout
- [ ] Passwords are never stored in plain text (verify in DB with `sqlite3` CLI)
- [ ] `GET /register` still renders the empty form unchanged
- [ ] App starts without errors (`python app.py`)
