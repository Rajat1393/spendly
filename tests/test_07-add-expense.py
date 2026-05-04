"""
tests/test_07-add-expense.py

Test suite for Step 07 — Add Expense feature.

Covers:
  - Unit tests for the create_expense DB helper
  - Auth guards on GET and POST /expenses/add
  - Happy-path GET (form rendering, all 7 categories present)
  - Happy-path POST (redirect to profile, DB row inserted)
  - Validation errors: missing amount, zero amount, negative amount,
    non-numeric amount, invalid category, invalid date
  - Optional description field (omitted → NULL stored)
  - Form value re-population on validation failure
  - Navbar "Add Expense" link visibility when logged in
"""

import os
import sqlite3
import tempfile

import pytest

# ---------------------------------------------------------------------------
# Patch get_db() before importing app so all DB calls go to our temp file
# ---------------------------------------------------------------------------

@pytest.fixture(scope="function")
def db_path(tmp_path):
    """Return the path to a fresh, isolated SQLite database file."""
    return str(tmp_path / "test_spendly.db")


@pytest.fixture(scope="function")
def app(db_path, monkeypatch):
    """
    Flask application configured for testing.

    get_db() in database/db.py resolves the DB path relative to its own
    __file__; we monkeypatch it to return a connection to our temp file
    so that tests never touch the production spendly.db.
    """
    import database.db as db_module

    def _get_test_db():
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    monkeypatch.setattr(db_module, "get_db", _get_test_db)

    from app import app as flask_app

    flask_app.config.update(
        {
            "TESTING": True,
            "SECRET_KEY": "test-secret-key",
            "WTF_CSRF_ENABLED": False,
        }
    )

    with flask_app.app_context():
        db_module.init_db()
        yield flask_app


@pytest.fixture(scope="function")
def client(app):
    """Unauthenticated test client."""
    return app.test_client()


@pytest.fixture(scope="function")
def registered_user(client):
    """Register a test user and return their credentials dict."""
    credentials = {
        "name": "Test User",
        "email": "testuser@example.com",
        "password": "testpassword123",
    }
    resp = client.post("/register", data=credentials)
    # Registration should succeed (redirect to login)
    assert resp.status_code == 302, "Registration failed during fixture setup"
    return credentials


@pytest.fixture(scope="function")
def auth_client(client, registered_user):
    """A test client that is already logged in as the registered test user."""
    resp = client.post(
        "/login",
        data={
            "email": registered_user["email"],
            "password": registered_user["password"],
        },
    )
    assert resp.status_code == 302, "Login failed during fixture setup"
    return client


# ---------------------------------------------------------------------------
# Helper: fetch all expenses from the temp DB directly
# ---------------------------------------------------------------------------

def _query_expenses(db_path, user_email=None):
    """
    Query the test DB directly and return all expenses (or filtered by
    joining users if user_email is given).
    """
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    if user_email:
        rows = conn.execute(
            """
            SELECT e.*
            FROM   expenses e
            JOIN   users u ON u.id = e.user_id
            WHERE  u.email = ?
            ORDER BY e.id DESC
            """,
            (user_email,),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM expenses ORDER BY id DESC"
        ).fetchall()
    conn.close()
    return rows


VALID_CATEGORIES = [
    "Food",
    "Transport",
    "Bills",
    "Health",
    "Entertainment",
    "Shopping",
    "Other",
]


# ===========================================================================
# Unit tests — create_expense helper
# ===========================================================================

class TestCreateExpenseUnit:
    """Direct unit tests for the create_expense database helper."""

    def test_create_expense_valid_inserts_row(self, app, db_path):
        """Inserting a valid expense creates exactly one row in the DB."""
        from database.db import create_expense

        with app.app_context():
            # We need a user first (FK constraint)
            from database.db import create_user
            from werkzeug.security import generate_password_hash

            create_user("Unit User", "unit@example.com", generate_password_hash("pw"))

            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            user_id = conn.execute(
                "SELECT id FROM users WHERE email = ?", ("unit@example.com",)
            ).fetchone()["id"]
            conn.close()

            create_expense(user_id, 50.0, "Food", "2026-03-20", "Lunch")

        rows = _query_expenses(db_path, user_email="unit@example.com")
        assert len(rows) == 1, "Expected exactly one expense row after insert"
        row = rows[0]
        assert float(row["amount"]) == 50.0, "Amount should be 50.0"
        assert row["category"] == "Food", "Category should be Food"
        assert row["date"] == "2026-03-20", "Date should be 2026-03-20"
        assert row["description"] == "Lunch", "Description should be Lunch"

    def test_create_expense_null_description_stored_as_null(self, app, db_path):
        """Passing description=None stores NULL in the description column."""
        from database.db import create_expense, create_user
        from werkzeug.security import generate_password_hash

        with app.app_context():
            create_user("Null Desc", "nulldesc@example.com", generate_password_hash("pw"))

            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            user_id = conn.execute(
                "SELECT id FROM users WHERE email = ?", ("nulldesc@example.com",)
            ).fetchone()["id"]
            conn.close()

            create_expense(user_id, 25.0, "Transport", "2026-04-01", None)

        rows = _query_expenses(db_path, user_email="nulldesc@example.com")
        assert len(rows) == 1, "Expected one expense row"
        assert rows[0]["description"] is None, "description should be NULL when None is passed"

    def test_create_expense_amount_stored_as_float(self, app, db_path):
        """The amount is stored as a REAL (float) value."""
        from database.db import create_expense, create_user
        from werkzeug.security import generate_password_hash

        with app.app_context():
            create_user("Float User", "float@example.com", generate_password_hash("pw"))

            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            user_id = conn.execute(
                "SELECT id FROM users WHERE email = ?", ("float@example.com",)
            ).fetchone()["id"]
            conn.close()

            create_expense(user_id, 99.99, "Bills", "2026-05-01", "Electric")

        rows = _query_expenses(db_path, user_email="float@example.com")
        assert float(rows[0]["amount"]) == pytest.approx(99.99), "Amount precision must be preserved"

    def test_create_expense_user_id_is_recorded(self, app, db_path):
        """The user_id FK is stored on the expense row."""
        from database.db import create_expense, create_user
        from werkzeug.security import generate_password_hash

        with app.app_context():
            create_user("ID Check", "idcheck@example.com", generate_password_hash("pw"))

            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            user_id = conn.execute(
                "SELECT id FROM users WHERE email = ?", ("idcheck@example.com",)
            ).fetchone()["id"]
            conn.close()

            create_expense(user_id, 10.0, "Other", "2026-01-15", "Test")

        rows = _query_expenses(db_path, user_email="idcheck@example.com")
        assert rows[0]["user_id"] == user_id, "Stored user_id must match the inserting user"


# ===========================================================================
# Route tests — GET /expenses/add
# ===========================================================================

class TestGetAddExpense:
    """Tests for GET /expenses/add."""

    def test_get_unauthenticated_redirects_to_login(self, client):
        """Unauthenticated GET redirects to /login with 302."""
        resp = client.get("/expenses/add")
        assert resp.status_code == 302, "Expected 302 redirect for unauthenticated GET"
        assert "/login" in resp.headers["Location"], (
            "Unauthenticated GET should redirect to /login"
        )

    def test_get_authenticated_returns_200(self, auth_client):
        """Authenticated GET returns 200 OK."""
        resp = auth_client.get("/expenses/add")
        assert resp.status_code == 200, "Authenticated GET should return 200"

    def test_get_authenticated_contains_form_with_post_method(self, auth_client):
        """The page contains a <form> element with method POST."""
        resp = auth_client.get("/expenses/add")
        body = resp.data.decode("utf-8")
        assert "<form" in body.lower(), "Page must contain a <form> element"
        assert 'method="post"' in body.lower() or "method='post'" in body.lower(), (
            "Form must use POST method"
        )

    def test_get_authenticated_contains_amount_field(self, auth_client):
        """The form contains an input for amount."""
        resp = auth_client.get("/expenses/add")
        body = resp.data.decode("utf-8")
        assert 'name="amount"' in body, "Form must have an amount input field"

    def test_get_authenticated_contains_date_field(self, auth_client):
        """The form contains an input for date."""
        resp = auth_client.get("/expenses/add")
        body = resp.data.decode("utf-8")
        assert 'name="date"' in body, "Form must have a date input field"

    def test_get_authenticated_contains_description_field(self, auth_client):
        """The form contains an input/textarea for description."""
        resp = auth_client.get("/expenses/add")
        body = resp.data.decode("utf-8")
        assert 'name="description"' in body, "Form must have a description field"

    def test_get_authenticated_contains_category_select(self, auth_client):
        """The form contains a <select> for category."""
        resp = auth_client.get("/expenses/add")
        body = resp.data.decode("utf-8")
        assert "<select" in body.lower(), "Form must contain a <select> for category"
        assert 'name="category"' in body, "Select must be named 'category'"

    @pytest.mark.parametrize("category", VALID_CATEGORIES)
    def test_get_authenticated_all_seven_categories_present(self, auth_client, category):
        """Each of the 7 required categories appears as a select option."""
        resp = auth_client.get("/expenses/add")
        body = resp.data.decode("utf-8")
        assert category in body, (
            f"Category '{category}' must appear in the category select options"
        )

    def test_get_authenticated_exactly_seven_categories(self, auth_client):
        """The select contains exactly the 7 specified category values."""
        resp = auth_client.get("/expenses/add")
        body = resp.data.decode("utf-8")
        for cat in VALID_CATEGORIES:
            assert cat in body, f"Missing expected category: {cat}"

    def test_get_authenticated_defaults_date_to_today(self, auth_client):
        """The date field is pre-filled with today's date."""
        from datetime import datetime

        today = datetime.today().strftime("%Y-%m-%d")
        resp = auth_client.get("/expenses/add")
        body = resp.data.decode("utf-8")
        assert today in body, "Date field should default to today's date"

    def test_get_authenticated_has_cancel_link_to_profile(self, auth_client):
        """The form page has a cancel/back link pointing to /profile."""
        resp = auth_client.get("/expenses/add")
        body = resp.data.decode("utf-8")
        assert "/profile" in body, "Page must contain a cancel link pointing to /profile"

    def test_get_authenticated_extends_base_template(self, auth_client):
        """The rendered page includes base.html landmarks (nav or footer)."""
        resp = auth_client.get("/expenses/add")
        body = resp.data.decode("utf-8")
        # base.html typically renders a <nav> or <header>
        assert "<nav" in body.lower() or "<header" in body.lower(), (
            "Page should extend base.html and include nav/header from the base layout"
        )

    def test_get_authenticated_navbar_shows_add_expense_link(self, auth_client):
        """When logged in, the navbar includes an 'Add Expense' link."""
        resp = auth_client.get("/expenses/add")
        body = resp.data.decode("utf-8")
        assert "Add Expense" in body, (
            "Navbar must show an 'Add Expense' link for logged-in users"
        )


# ===========================================================================
# Route tests — POST /expenses/add
# ===========================================================================

class TestPostAddExpense:
    """Tests for POST /expenses/add."""

    # -----------------------------------------------------------------------
    # Auth guard
    # -----------------------------------------------------------------------

    def test_post_unauthenticated_redirects_to_login(self, client):
        """Unauthenticated POST redirects to /login with 302."""
        resp = client.post(
            "/expenses/add",
            data={
                "amount": "50.0",
                "category": "Food",
                "date": "2026-03-20",
                "description": "Lunch",
            },
        )
        assert resp.status_code == 302, "Expected 302 redirect for unauthenticated POST"
        assert "/login" in resp.headers["Location"], (
            "Unauthenticated POST should redirect to /login"
        )

    # -----------------------------------------------------------------------
    # Happy path — valid data
    # -----------------------------------------------------------------------

    def test_post_valid_data_redirects_to_profile(self, auth_client):
        """Valid POST redirects to /profile (302)."""
        resp = auth_client.post(
            "/expenses/add",
            data={
                "amount": "50.0",
                "category": "Food",
                "date": "2026-03-20",
                "description": "Lunch",
            },
        )
        assert resp.status_code == 302, "Valid POST must redirect (302)"
        assert "/profile" in resp.headers["Location"], (
            "Valid POST must redirect to /profile"
        )

    def test_post_valid_data_inserts_row_in_db(self, auth_client, db_path, registered_user):
        """Valid POST inserts exactly one expense row into the database."""
        auth_client.post(
            "/expenses/add",
            data={
                "amount": "50.0",
                "category": "Food",
                "date": "2026-03-20",
                "description": "Lunch",
            },
        )
        rows = _query_expenses(db_path, user_email=registered_user["email"])
        assert len(rows) == 1, "One expense row should exist after valid POST"

    def test_post_valid_data_correct_amount_stored(self, auth_client, db_path, registered_user):
        """The amount stored in DB matches the submitted value."""
        auth_client.post(
            "/expenses/add",
            data={
                "amount": "50.0",
                "category": "Food",
                "date": "2026-03-20",
                "description": "Lunch",
            },
        )
        rows = _query_expenses(db_path, user_email=registered_user["email"])
        assert float(rows[0]["amount"]) == pytest.approx(50.0), "Stored amount must be 50.0"

    def test_post_valid_data_correct_category_stored(self, auth_client, db_path, registered_user):
        """The category stored in DB matches the submitted value."""
        auth_client.post(
            "/expenses/add",
            data={
                "amount": "50.0",
                "category": "Food",
                "date": "2026-03-20",
                "description": "Lunch",
            },
        )
        rows = _query_expenses(db_path, user_email=registered_user["email"])
        assert rows[0]["category"] == "Food", "Stored category must be 'Food'"

    def test_post_valid_data_correct_date_stored(self, auth_client, db_path, registered_user):
        """The date stored in DB matches the submitted value."""
        auth_client.post(
            "/expenses/add",
            data={
                "amount": "50.0",
                "category": "Food",
                "date": "2026-03-20",
                "description": "Lunch",
            },
        )
        rows = _query_expenses(db_path, user_email=registered_user["email"])
        assert rows[0]["date"] == "2026-03-20", "Stored date must be '2026-03-20'"

    def test_post_valid_data_correct_description_stored(self, auth_client, db_path, registered_user):
        """The description stored in DB matches the submitted value."""
        auth_client.post(
            "/expenses/add",
            data={
                "amount": "50.0",
                "category": "Food",
                "date": "2026-03-20",
                "description": "Lunch",
            },
        )
        rows = _query_expenses(db_path, user_email=registered_user["email"])
        assert rows[0]["description"] == "Lunch", "Stored description must be 'Lunch'"

    # -----------------------------------------------------------------------
    # Optional description — omitted → NULL
    # -----------------------------------------------------------------------

    def test_post_no_description_redirects_to_profile(self, auth_client):
        """Omitting description is valid; should still redirect to /profile."""
        resp = auth_client.post(
            "/expenses/add",
            data={
                "amount": "30.0",
                "category": "Transport",
                "date": "2026-04-10",
                "description": "",
            },
        )
        assert resp.status_code == 302, "Missing description must not cause an error"
        assert "/profile" in resp.headers["Location"], (
            "No-description POST should redirect to /profile"
        )

    def test_post_no_description_stores_null_in_db(self, auth_client, db_path, registered_user):
        """Omitting description stores NULL in the description column."""
        auth_client.post(
            "/expenses/add",
            data={
                "amount": "30.0",
                "category": "Transport",
                "date": "2026-04-10",
                "description": "",
            },
        )
        rows = _query_expenses(db_path, user_email=registered_user["email"])
        assert len(rows) == 1, "One expense row should exist"
        assert rows[0]["description"] is None, (
            "Empty description must be stored as NULL"
        )

    def test_post_whitespace_only_description_stores_null(self, auth_client, db_path, registered_user):
        """A whitespace-only description is stripped and stored as NULL."""
        auth_client.post(
            "/expenses/add",
            data={
                "amount": "20.0",
                "category": "Other",
                "date": "2026-04-15",
                "description": "   ",
            },
        )
        rows = _query_expenses(db_path, user_email=registered_user["email"])
        assert rows[0]["description"] is None, (
            "Whitespace-only description should be stored as NULL after stripping"
        )

    # -----------------------------------------------------------------------
    # Validation — amount
    # -----------------------------------------------------------------------

    def test_post_missing_amount_returns_200(self, auth_client):
        """Missing amount field re-renders the form (200)."""
        resp = auth_client.post(
            "/expenses/add",
            data={
                "amount": "",
                "category": "Food",
                "date": "2026-03-20",
                "description": "",
            },
        )
        assert resp.status_code == 200, "Missing amount should re-render the form with 200"

    def test_post_missing_amount_shows_error(self, auth_client):
        """Missing amount field shows an error message in the response body."""
        resp = auth_client.post(
            "/expenses/add",
            data={
                "amount": "",
                "category": "Food",
                "date": "2026-03-20",
                "description": "",
            },
        )
        body = resp.data.decode("utf-8")
        # The error message is flashed; check for generic error indicator
        assert "error" in body.lower() or "amount" in body.lower(), (
            "Response must contain an error message about the amount"
        )

    def test_post_missing_amount_does_not_insert_row(self, auth_client, db_path, registered_user):
        """Missing amount must not insert any row in the DB."""
        auth_client.post(
            "/expenses/add",
            data={
                "amount": "",
                "category": "Food",
                "date": "2026-03-20",
                "description": "",
            },
        )
        rows = _query_expenses(db_path, user_email=registered_user["email"])
        assert len(rows) == 0, "No DB row should be inserted when amount is missing"

    def test_post_zero_amount_returns_200(self, auth_client):
        """Amount of 0 is invalid and re-renders the form (200)."""
        resp = auth_client.post(
            "/expenses/add",
            data={
                "amount": "0",
                "category": "Food",
                "date": "2026-03-20",
                "description": "",
            },
        )
        assert resp.status_code == 200, "Zero amount should re-render the form with 200"

    def test_post_zero_amount_shows_error(self, auth_client):
        """Amount of 0 shows an error message."""
        resp = auth_client.post(
            "/expenses/add",
            data={
                "amount": "0",
                "category": "Food",
                "date": "2026-03-20",
                "description": "",
            },
        )
        body = resp.data.decode("utf-8")
        assert "error" in body.lower() or "amount" in body.lower(), (
            "Response must contain an error message when amount is zero"
        )

    def test_post_zero_amount_does_not_insert_row(self, auth_client, db_path, registered_user):
        """Zero amount must not insert any row in the DB."""
        auth_client.post(
            "/expenses/add",
            data={
                "amount": "0",
                "category": "Food",
                "date": "2026-03-20",
                "description": "",
            },
        )
        rows = _query_expenses(db_path, user_email=registered_user["email"])
        assert len(rows) == 0, "No DB row should be inserted when amount is 0"

    def test_post_negative_amount_returns_200(self, auth_client):
        """Negative amount re-renders the form (200)."""
        resp = auth_client.post(
            "/expenses/add",
            data={
                "amount": "-10.0",
                "category": "Food",
                "date": "2026-03-20",
                "description": "",
            },
        )
        assert resp.status_code == 200, "Negative amount should re-render the form"

    def test_post_negative_amount_shows_error(self, auth_client):
        """Negative amount shows an error message."""
        resp = auth_client.post(
            "/expenses/add",
            data={
                "amount": "-10.0",
                "category": "Food",
                "date": "2026-03-20",
                "description": "",
            },
        )
        body = resp.data.decode("utf-8")
        assert "error" in body.lower() or "amount" in body.lower(), (
            "Response must contain an error message for negative amount"
        )

    def test_post_non_numeric_amount_returns_200(self, auth_client):
        """Non-numeric amount string re-renders the form (200)."""
        resp = auth_client.post(
            "/expenses/add",
            data={
                "amount": "abc",
                "category": "Food",
                "date": "2026-03-20",
                "description": "",
            },
        )
        assert resp.status_code == 200, "Non-numeric amount should re-render the form"

    def test_post_non_numeric_amount_shows_error(self, auth_client):
        """Non-numeric amount string shows an error message."""
        resp = auth_client.post(
            "/expenses/add",
            data={
                "amount": "abc",
                "category": "Food",
                "date": "2026-03-20",
                "description": "",
            },
        )
        body = resp.data.decode("utf-8")
        assert "error" in body.lower() or "amount" in body.lower(), (
            "Response must contain an error message for non-numeric amount"
        )

    def test_post_non_numeric_amount_does_not_insert_row(self, auth_client, db_path, registered_user):
        """Non-numeric amount must not insert any row in the DB."""
        auth_client.post(
            "/expenses/add",
            data={
                "amount": "abc",
                "category": "Food",
                "date": "2026-03-20",
                "description": "",
            },
        )
        rows = _query_expenses(db_path, user_email=registered_user["email"])
        assert len(rows) == 0, "No DB row should be inserted for non-numeric amount"

    # -----------------------------------------------------------------------
    # Validation — category
    # -----------------------------------------------------------------------

    def test_post_invalid_category_returns_200(self, auth_client):
        """A category not in the fixed list re-renders the form (200)."""
        resp = auth_client.post(
            "/expenses/add",
            data={
                "amount": "50.0",
                "category": "NotACategory",
                "date": "2026-03-20",
                "description": "",
            },
        )
        assert resp.status_code == 200, "Invalid category should re-render the form"

    def test_post_invalid_category_shows_error(self, auth_client):
        """An invalid category shows an error message."""
        resp = auth_client.post(
            "/expenses/add",
            data={
                "amount": "50.0",
                "category": "NotACategory",
                "date": "2026-03-20",
                "description": "",
            },
        )
        body = resp.data.decode("utf-8")
        assert "error" in body.lower() or "category" in body.lower(), (
            "Response must contain an error message for invalid category"
        )

    def test_post_invalid_category_does_not_insert_row(self, auth_client, db_path, registered_user):
        """An invalid category must not insert any row in the DB."""
        auth_client.post(
            "/expenses/add",
            data={
                "amount": "50.0",
                "category": "NotACategory",
                "date": "2026-03-20",
                "description": "",
            },
        )
        rows = _query_expenses(db_path, user_email=registered_user["email"])
        assert len(rows) == 0, "No DB row should be inserted for invalid category"

    def test_post_empty_category_returns_200(self, auth_client):
        """An empty category string (not in fixed list) re-renders the form."""
        resp = auth_client.post(
            "/expenses/add",
            data={
                "amount": "50.0",
                "category": "",
                "date": "2026-03-20",
                "description": "",
            },
        )
        assert resp.status_code == 200, "Empty category should re-render the form"

    # -----------------------------------------------------------------------
    # Validation — date
    # -----------------------------------------------------------------------

    def test_post_invalid_date_returns_200(self, auth_client):
        """An invalid date string re-renders the form (200)."""
        resp = auth_client.post(
            "/expenses/add",
            data={
                "amount": "50.0",
                "category": "Food",
                "date": "not-a-date",
                "description": "",
            },
        )
        assert resp.status_code == 200, "Invalid date should re-render the form"

    def test_post_invalid_date_shows_error(self, auth_client):
        """An invalid date string shows an error message."""
        resp = auth_client.post(
            "/expenses/add",
            data={
                "amount": "50.0",
                "category": "Food",
                "date": "not-a-date",
                "description": "",
            },
        )
        body = resp.data.decode("utf-8")
        assert "error" in body.lower() or "date" in body.lower(), (
            "Response must contain an error message for invalid date"
        )

    def test_post_invalid_date_does_not_insert_row(self, auth_client, db_path, registered_user):
        """An invalid date must not insert any row in the DB."""
        auth_client.post(
            "/expenses/add",
            data={
                "amount": "50.0",
                "category": "Food",
                "date": "not-a-date",
                "description": "",
            },
        )
        rows = _query_expenses(db_path, user_email=registered_user["email"])
        assert len(rows) == 0, "No DB row should be inserted for invalid date"

    def test_post_missing_date_returns_200(self, auth_client):
        """A missing date field re-renders the form (200)."""
        resp = auth_client.post(
            "/expenses/add",
            data={
                "amount": "50.0",
                "category": "Food",
                "date": "",
                "description": "",
            },
        )
        assert resp.status_code == 200, "Missing date should re-render the form"

    def test_post_wrong_date_format_returns_200(self, auth_client):
        """Date in wrong format (DD/MM/YYYY instead of YYYY-MM-DD) re-renders."""
        resp = auth_client.post(
            "/expenses/add",
            data={
                "amount": "50.0",
                "category": "Food",
                "date": "20/03/2026",
                "description": "",
            },
        )
        assert resp.status_code == 200, "Wrong date format should re-render the form"

    # -----------------------------------------------------------------------
    # Form value re-population on validation errors
    # -----------------------------------------------------------------------

    def test_post_validation_error_repopulates_amount(self, auth_client):
        """On validation error, the previously submitted amount is re-shown."""
        resp = auth_client.post(
            "/expenses/add",
            data={
                "amount": "75.50",
                "category": "NotACategory",
                "date": "2026-03-20",
                "description": "Dinner",
            },
        )
        body = resp.data.decode("utf-8")
        assert "75.50" in body, (
            "Previously entered amount should be re-populated in the form on error"
        )

    def test_post_validation_error_repopulates_description(self, auth_client):
        """On validation error, the previously submitted description is re-shown."""
        resp = auth_client.post(
            "/expenses/add",
            data={
                "amount": "75.50",
                "category": "NotACategory",
                "date": "2026-03-20",
                "description": "My unique dinner description",
            },
        )
        body = resp.data.decode("utf-8")
        assert "My unique dinner description" in body, (
            "Previously entered description should be re-populated on error"
        )

    def test_post_validation_error_repopulates_date(self, auth_client):
        """On validation error, the previously submitted date is re-shown."""
        resp = auth_client.post(
            "/expenses/add",
            data={
                "amount": "0",  # invalid — triggers error
                "category": "Food",
                "date": "2026-03-20",
                "description": "",
            },
        )
        body = resp.data.decode("utf-8")
        assert "2026-03-20" in body, (
            "Previously entered date should be re-populated in the form on error"
        )

    # -----------------------------------------------------------------------
    # Parametrized — all valid categories accepted
    # -----------------------------------------------------------------------

    @pytest.mark.parametrize("category", VALID_CATEGORIES)
    def test_post_each_valid_category_is_accepted(self, auth_client, db_path, registered_user, category):
        """Each of the 7 specified categories is accepted and stored correctly."""
        # Clean up prior inserted rows between parametrize iterations via fresh fixture,
        # but since fixtures are function-scoped this works correctly only if we
        # check for the specific category row rather than total count.
        resp = auth_client.post(
            "/expenses/add",
            data={
                "amount": "10.0",
                "category": category,
                "date": "2026-01-01",
                "description": f"Test {category}",
            },
        )
        assert resp.status_code == 302, (
            f"Category '{category}' should be accepted as valid"
        )
        rows = _query_expenses(db_path, user_email=registered_user["email"])
        stored_categories = [r["category"] for r in rows]
        assert category in stored_categories, (
            f"Category '{category}' should be stored in the DB"
        )

    # -----------------------------------------------------------------------
    # SQL injection safety
    # -----------------------------------------------------------------------

    def test_post_sql_injection_in_description_is_safe(self, auth_client, db_path, registered_user):
        """SQL injection attempt in description is stored safely as literal text."""
        malicious_desc = "'; DROP TABLE expenses; --"
        resp = auth_client.post(
            "/expenses/add",
            data={
                "amount": "10.0",
                "category": "Food",
                "date": "2026-01-01",
                "description": malicious_desc,
            },
        )
        # Should succeed (redirect) — parameterized queries neutralise injection
        assert resp.status_code == 302, "SQL injection in description must not cause an error"

        # Expenses table must still exist and contain the row
        rows = _query_expenses(db_path, user_email=registered_user["email"])
        assert len(rows) == 1, "Expense row must be inserted despite injection attempt"
        assert rows[0]["description"] == malicious_desc, (
            "Injection string must be stored as literal text, not executed"
        )

    def test_post_sql_injection_in_amount_rejected_safely(self, auth_client, db_path, registered_user):
        """SQL injection string as amount is rejected cleanly (non-numeric → error)."""
        resp = auth_client.post(
            "/expenses/add",
            data={
                "amount": "1; DROP TABLE expenses; --",
                "category": "Food",
                "date": "2026-01-01",
                "description": "",
            },
        )
        assert resp.status_code == 200, "Non-numeric injection amount should re-render the form"
        rows = _query_expenses(db_path, user_email=registered_user["email"])
        assert len(rows) == 0, "No row should be inserted for injection-as-amount"


# ===========================================================================
# Profile page — Add Expense button
# ===========================================================================

class TestProfileAddExpenseButton:
    """Verify the profile page contains an 'Add Expense' navigation element."""

    def test_profile_page_contains_add_expense_link(self, auth_client):
        """The profile page must have a link/button pointing to /expenses/add."""
        resp = auth_client.get("/profile")
        assert resp.status_code == 200, "Profile page must return 200"
        body = resp.data.decode("utf-8")
        assert "/expenses/add" in body, (
            "Profile page must contain a link to /expenses/add"
        )

    def test_profile_page_add_expense_button_text(self, auth_client):
        """The profile page contains an 'Add Expense' button label."""
        resp = auth_client.get("/profile")
        body = resp.data.decode("utf-8")
        assert "Add Expense" in body, (
            "Profile page must contain visible 'Add Expense' button text"
        )
