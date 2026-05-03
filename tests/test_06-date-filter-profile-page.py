"""
tests/test_06-date-filter-profile-page.py

Tests for Step 6: Date-filter feature on the /profile route.

All test logic is derived from the spec
  .claude/specs/06-date-filter-profile-page.md
and the Definition of Done contained there.

No implementation details are assumed beyond what the spec describes.
"""

import sqlite3
from datetime import datetime, date, timedelta
import pytest
from werkzeug.security import generate_password_hash

from app import app as flask_app
from database.db import get_db, init_db


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _first_of_month(today: date) -> str:
    return today.replace(day=1).isoformat()


def _months_ago(today: date, n: int) -> str:
    """Return the first day of the month that is n months before today."""
    month = today.month - n
    year = today.year + (month - 1) // 12
    month = ((month - 1) % 12) + 1
    return date(year, month, 1).isoformat()


def _today_str() -> str:
    return date.today().isoformat()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def app(tmp_path):
    """Isolated Flask app using a temp-file SQLite DB (not :memory:, so that
    get_db() inside route handlers can open the same file)."""
    db_file = tmp_path / "test_spendly.db"

    flask_app.config.update(
        {
            "TESTING": True,
            "SECRET_KEY": "test-secret-key",
            "WTF_CSRF_ENABLED": False,
            # Point get_db() at the temp file by monkey-patching the env var
            # that db.py falls back to — we do this by overriding get_db at the
            # module level inside the app context.
        }
    )

    # Patch get_db to use the temp file for this test session.
    import database.db as db_module

    original_get_db = db_module.get_db

    def patched_get_db():
        conn = sqlite3.connect(str(db_file))
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    db_module.get_db = patched_get_db

    with flask_app.app_context():
        init_db()
        yield flask_app

    db_module.get_db = original_get_db


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def seeded_user_id(app):
    """Insert a test user and return their id."""
    from database.db import get_db as gdb

    conn = gdb()
    conn.execute(
        "INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)",
        ("Test User", "test@spendly.com", generate_password_hash("password")),
    )
    conn.commit()
    user_id = conn.execute(
        "SELECT id FROM users WHERE email = ?", ("test@spendly.com",)
    ).fetchone()["id"]
    conn.close()
    return user_id


@pytest.fixture
def seeded_expenses(app, seeded_user_id):
    """
    Insert expenses at deterministic dates relative to today so that filter
    assertions are stable regardless of when the tests run.

    Buckets:
      - this_month   : first day of current month
      - last_3_months: exactly 60 days ago  (always within 3-month window)
      - last_6_months: exactly 150 days ago (always within 6-month window)
      - old          : exactly 400 days ago (outside every preset window)
    """
    today = date.today()
    this_month_date = today.replace(day=1).isoformat()
    last_3m_date = (today - timedelta(days=60)).isoformat()
    last_6m_date = (today - timedelta(days=150)).isoformat()
    old_date = (today - timedelta(days=400)).isoformat()

    from database.db import get_db as gdb

    conn = gdb()
    conn.executemany(
        "INSERT INTO expenses (user_id, amount, category, date, description)"
        " VALUES (?, ?, ?, ?, ?)",
        [
            (seeded_user_id, 100.00, "Food", this_month_date, "This month expense"),
            (seeded_user_id, 200.00, "Transport", last_3m_date, "3-month expense"),
            (seeded_user_id, 300.00, "Bills", last_6m_date, "6-month expense"),
            (seeded_user_id, 400.00, "Shopping", old_date, "Old expense"),
        ],
    )
    conn.commit()
    conn.close()

    return {
        "user_id": seeded_user_id,
        "this_month_date": this_month_date,
        "last_3m_date": last_3m_date,
        "last_6m_date": last_6m_date,
        "old_date": old_date,
        "total_all_time": 1000.00,
    }


@pytest.fixture
def auth_client(client, seeded_user_id):
    """Test client pre-authenticated as the seeded test user."""
    with client.session_transaction() as sess:
        sess["user_id"] = seeded_user_id
        sess["user_name"] = "Test User"
    return client


# ---------------------------------------------------------------------------
# 1. Auth guard
# ---------------------------------------------------------------------------

class TestAuthGuard:
    def test_unauthenticated_profile_redirects_to_login(self, client):
        """An unauthenticated GET /profile must redirect to /login."""
        response = client.get("/profile")
        assert response.status_code == 302, (
            "Expected redirect (302) for unauthenticated /profile"
        )
        assert "/login" in response.headers["Location"], (
            "Redirect target must be /login"
        )

    def test_unauthenticated_profile_with_params_redirects_to_login(self, client):
        """Even with date params, unauthenticated requests must redirect."""
        response = client.get("/profile?date_from=2026-01-01&date_to=2026-01-31")
        assert response.status_code == 302, (
            "Expected redirect (302) for unauthenticated /profile with params"
        )
        assert "/login" in response.headers["Location"], (
            "Redirect target must be /login"
        )


# ---------------------------------------------------------------------------
# 2. No-params baseline (All Time, unfiltered)
# ---------------------------------------------------------------------------

class TestNoParamsBaseline:
    def test_profile_no_params_returns_200(self, auth_client, seeded_expenses):
        """GET /profile with no params must return HTTP 200."""
        response = auth_client.get("/profile")
        assert response.status_code == 200, (
            "Expected 200 for authenticated /profile with no params"
        )

    def test_profile_no_params_shows_all_time_total(self, auth_client, seeded_expenses):
        """Unfiltered /profile must include total of all expenses."""
        response = auth_client.get("/profile")
        data = response.data.decode("utf-8")
        # Total of all 4 seeded expenses = ₹1,000.00
        assert "1,000.00" in data, (
            "All-time total ₹1,000.00 must appear on unfiltered profile page"
        )

    def test_profile_no_params_shows_all_transactions(self, auth_client, seeded_expenses):
        """Unfiltered profile must show all 4 seeded transactions."""
        response = auth_client.get("/profile")
        data = response.data.decode("utf-8")
        # The old expense description is unique to unfiltered view
        assert "Old expense" in data, (
            "Old expense must appear on unfiltered profile page"
        )

    def test_profile_no_params_shows_rupee_symbol(self, auth_client, seeded_expenses):
        """All amounts must display the ₹ symbol on the unfiltered view."""
        response = auth_client.get("/profile")
        data = response.data.decode("utf-8")
        assert "₹" in data, "₹ symbol must appear on the unfiltered profile page"


# ---------------------------------------------------------------------------
# 3. Empty params — All Time via ?date_from=&date_to=
# ---------------------------------------------------------------------------

class TestEmptyParams:
    def test_empty_params_returns_200(self, auth_client, seeded_expenses):
        """GET /profile?date_from=&date_to= must return HTTP 200 without crash."""
        response = auth_client.get("/profile?date_from=&date_to=")
        assert response.status_code == 200, (
            "Empty date params must not crash the app — expected 200"
        )

    def test_empty_params_shows_all_time_data(self, auth_client, seeded_expenses):
        """Empty params must behave like no params (unfiltered, all expenses)."""
        response = auth_client.get("/profile?date_from=&date_to=")
        data = response.data.decode("utf-8")
        assert "1,000.00" in data, (
            "Empty date params must return unfiltered all-time total"
        )

    def test_empty_params_shows_rupee_symbol(self, auth_client, seeded_expenses):
        """₹ symbol must appear even when both params are empty strings."""
        response = auth_client.get("/profile?date_from=&date_to=")
        data = response.data.decode("utf-8")
        assert "₹" in data, "₹ symbol must appear with empty date params"


# ---------------------------------------------------------------------------
# 4. This Month filter
# ---------------------------------------------------------------------------

class TestThisMonthFilter:
    def test_this_month_returns_200(self, auth_client, seeded_expenses):
        today = _today_str()
        first = _first_of_month(date.today())
        response = auth_client.get(f"/profile?date_from={first}&date_to={today}")
        assert response.status_code == 200, "This Month filter must return 200"

    def test_this_month_includes_this_month_expense(self, auth_client, seeded_expenses):
        today = _today_str()
        first = _first_of_month(date.today())
        response = auth_client.get(f"/profile?date_from={first}&date_to={today}")
        data = response.data.decode("utf-8")
        assert "This month expense" in data, (
            "Expense from first of current month must appear in This Month filter"
        )

    def test_this_month_excludes_old_expense(self, auth_client, seeded_expenses):
        today = _today_str()
        first = _first_of_month(date.today())
        response = auth_client.get(f"/profile?date_from={first}&date_to={today}")
        data = response.data.decode("utf-8")
        assert "Old expense" not in data, (
            "Expense from 400 days ago must NOT appear in This Month filter"
        )

    def test_this_month_total_is_only_this_month_amount(
        self, auth_client, seeded_expenses
    ):
        today = _today_str()
        first = _first_of_month(date.today())
        response = auth_client.get(f"/profile?date_from={first}&date_to={today}")
        data = response.data.decode("utf-8")
        # Only the ₹100.00 this-month expense should be in total
        assert "100.00" in data, (
            "This Month total must reflect only the expense dated in the current month"
        )

    def test_this_month_shows_rupee_symbol(self, auth_client, seeded_expenses):
        today = _today_str()
        first = _first_of_month(date.today())
        response = auth_client.get(f"/profile?date_from={first}&date_to={today}")
        data = response.data.decode("utf-8")
        assert "₹" in data, "₹ symbol must appear under This Month filter"


# ---------------------------------------------------------------------------
# 5. Last 3 Months filter
# ---------------------------------------------------------------------------

class TestLast3MonthsFilter:
    def test_last_3_months_returns_200(self, auth_client, seeded_expenses):
        today = _today_str()
        start = _months_ago(date.today(), 3)
        response = auth_client.get(f"/profile?date_from={start}&date_to={today}")
        assert response.status_code == 200, "Last 3 Months filter must return 200"

    def test_last_3_months_includes_60_day_old_expense(
        self, auth_client, seeded_expenses
    ):
        today = _today_str()
        start = _months_ago(date.today(), 3)
        response = auth_client.get(f"/profile?date_from={start}&date_to={today}")
        data = response.data.decode("utf-8")
        assert "3-month expense" in data, (
            "Expense from 60 days ago must appear in Last 3 Months filter"
        )

    def test_last_3_months_excludes_old_expense(self, auth_client, seeded_expenses):
        today = _today_str()
        start = _months_ago(date.today(), 3)
        response = auth_client.get(f"/profile?date_from={start}&date_to={today}")
        data = response.data.decode("utf-8")
        assert "Old expense" not in data, (
            "Expense from 400 days ago must NOT appear in Last 3 Months filter"
        )

    def test_last_3_months_shows_rupee_symbol(self, auth_client, seeded_expenses):
        today = _today_str()
        start = _months_ago(date.today(), 3)
        response = auth_client.get(f"/profile?date_from={start}&date_to={today}")
        data = response.data.decode("utf-8")
        assert "₹" in data, "₹ symbol must appear under Last 3 Months filter"


# ---------------------------------------------------------------------------
# 6. Last 6 Months filter
# ---------------------------------------------------------------------------

class TestLast6MonthsFilter:
    def test_last_6_months_returns_200(self, auth_client, seeded_expenses):
        today = _today_str()
        start = _months_ago(date.today(), 6)
        response = auth_client.get(f"/profile?date_from={start}&date_to={today}")
        assert response.status_code == 200, "Last 6 Months filter must return 200"

    def test_last_6_months_includes_150_day_old_expense(
        self, auth_client, seeded_expenses
    ):
        today = _today_str()
        start = _months_ago(date.today(), 6)
        response = auth_client.get(f"/profile?date_from={start}&date_to={today}")
        data = response.data.decode("utf-8")
        assert "6-month expense" in data, (
            "Expense from 150 days ago must appear in Last 6 Months filter"
        )

    def test_last_6_months_excludes_old_expense(self, auth_client, seeded_expenses):
        today = _today_str()
        start = _months_ago(date.today(), 6)
        response = auth_client.get(f"/profile?date_from={start}&date_to={today}")
        data = response.data.decode("utf-8")
        assert "Old expense" not in data, (
            "Expense from 400 days ago must NOT appear in Last 6 Months filter"
        )

    def test_last_6_months_shows_rupee_symbol(self, auth_client, seeded_expenses):
        today = _today_str()
        start = _months_ago(date.today(), 6)
        response = auth_client.get(f"/profile?date_from={start}&date_to={today}")
        data = response.data.decode("utf-8")
        assert "₹" in data, "₹ symbol must appear under Last 6 Months filter"


# ---------------------------------------------------------------------------
# 7. Custom valid date range
# ---------------------------------------------------------------------------

class TestCustomValidDateRange:
    def test_custom_range_returns_200(self, auth_client, seeded_expenses):
        """A custom valid date range must return HTTP 200."""
        expenses = seeded_expenses
        response = auth_client.get(
            f"/profile?date_from={expenses['last_3m_date']}"
            f"&date_to={expenses['last_3m_date']}"
        )
        assert response.status_code == 200, "Custom valid date range must return 200"

    def test_custom_range_shows_only_matching_expense(
        self, auth_client, seeded_expenses
    ):
        """Custom range pinpointing the 3-month expense date must include it."""
        expenses = seeded_expenses
        response = auth_client.get(
            f"/profile?date_from={expenses['last_3m_date']}"
            f"&date_to={expenses['last_3m_date']}"
        )
        data = response.data.decode("utf-8")
        assert "3-month expense" in data, (
            "Expense on the exact custom from=to date must appear"
        )

    def test_custom_range_excludes_out_of_range_expenses(
        self, auth_client, seeded_expenses
    ):
        """Expenses outside the custom range must not appear."""
        expenses = seeded_expenses
        response = auth_client.get(
            f"/profile?date_from={expenses['last_3m_date']}"
            f"&date_to={expenses['last_3m_date']}"
        )
        data = response.data.decode("utf-8")
        assert "This month expense" not in data, (
            "This-month expense must not appear when custom range targets 3-month date"
        )
        assert "Old expense" not in data, (
            "Old expense must not appear in custom range that targets 3-month date"
        )

    def test_custom_range_total_matches_expense_in_range(
        self, auth_client, seeded_expenses
    ):
        """Total spent must equal only the matched expense amount (₹200.00)."""
        expenses = seeded_expenses
        response = auth_client.get(
            f"/profile?date_from={expenses['last_3m_date']}"
            f"&date_to={expenses['last_3m_date']}"
        )
        data = response.data.decode("utf-8")
        assert "200.00" in data, (
            "Total for custom range covering only the 3-month expense must be ₹200.00"
        )

    def test_custom_range_shows_rupee_symbol(self, auth_client, seeded_expenses):
        expenses = seeded_expenses
        response = auth_client.get(
            f"/profile?date_from={expenses['last_3m_date']}"
            f"&date_to={expenses['last_3m_date']}"
        )
        data = response.data.decode("utf-8")
        assert "₹" in data, "₹ symbol must appear under a custom valid date range"


# ---------------------------------------------------------------------------
# 8. Inverted date range (date_from > date_to)
# ---------------------------------------------------------------------------

class TestInvertedDateRange:
    def test_inverted_range_returns_200(self, auth_client, seeded_expenses):
        """date_from > date_to must return HTTP 200, not an error page."""
        response = auth_client.get("/profile?date_from=2026-12-31&date_to=2026-01-01")
        assert response.status_code == 200, (
            "Inverted date range must return 200, not crash"
        )

    def test_inverted_range_flashes_error_message(self, auth_client, seeded_expenses):
        """A flash message 'Start date must be before end date.' must appear."""
        response = auth_client.get(
            "/profile?date_from=2026-12-31&date_to=2026-01-01",
            follow_redirects=True,
        )
        data = response.data.decode("utf-8")
        assert "Start date must be before end date." in data, (
            "Flash error message must appear when date_from > date_to"
        )

    def test_inverted_range_falls_back_to_unfiltered(
        self, auth_client, seeded_expenses
    ):
        """After an inverted range, the view must show all-time (unfiltered) data."""
        response = auth_client.get(
            "/profile?date_from=2026-12-31&date_to=2026-01-01"
        )
        data = response.data.decode("utf-8")
        # All-time total is ₹1,000.00; if filtered it would be different
        assert "1,000.00" in data, (
            "Inverted date range must fall back to unfiltered all-time total"
        )

    def test_inverted_range_shows_rupee_symbol(self, auth_client, seeded_expenses):
        response = auth_client.get("/profile?date_from=2026-12-31&date_to=2026-01-01")
        data = response.data.decode("utf-8")
        assert "₹" in data, "₹ symbol must appear even after inverted-range fallback"


# ---------------------------------------------------------------------------
# 9. Malformed date string
# ---------------------------------------------------------------------------

class TestMalformedDate:
    def test_malformed_date_from_does_not_crash(self, auth_client, seeded_expenses):
        """A garbage date_from value must not crash the app — returns 200."""
        response = auth_client.get("/profile?date_from=not-a-date&date_to=2026-01-31")
        assert response.status_code == 200, (
            "Malformed date_from must be silently ignored — expected 200"
        )

    def test_malformed_date_to_does_not_crash(self, auth_client, seeded_expenses):
        """A garbage date_to value must not crash the app — returns 200."""
        response = auth_client.get("/profile?date_from=2026-01-01&date_to=not-a-date")
        assert response.status_code == 200, (
            "Malformed date_to must be silently ignored — expected 200"
        )

    def test_both_malformed_dates_do_not_crash(self, auth_client, seeded_expenses):
        """Both params malformed must fall back to unfiltered view, returns 200."""
        response = auth_client.get(
            "/profile?date_from=abc&date_to=xyz"
        )
        assert response.status_code == 200, (
            "Both malformed date params must be silently ignored — expected 200"
        )

    def test_malformed_date_from_falls_back_to_unfiltered(
        self, auth_client, seeded_expenses
    ):
        """Malformed date_from should fall back to unfiltered, showing all expenses."""
        response = auth_client.get("/profile?date_from=not-a-date")
        data = response.data.decode("utf-8")
        assert "1,000.00" in data, (
            "Malformed date_from must fall back to all-time unfiltered total"
        )

    @pytest.mark.parametrize(
        "bad_from",
        [
            "not-a-date",
            "32-13-2026",
            "2026/01/01",
            "yesterday",
            "20260101",
            "",
        ],
    )
    def test_various_malformed_date_from_values(
        self, auth_client, seeded_expenses, bad_from
    ):
        """Parametrized: many garbage date_from values must all return 200."""
        response = auth_client.get(
            f"/profile?date_from={bad_from}&date_to=2026-12-31"
        )
        assert response.status_code == 200, (
            f"Malformed date_from='{bad_from}' must not crash the app"
        )


# ---------------------------------------------------------------------------
# 10. User with no expenses in range
# ---------------------------------------------------------------------------

class TestNoExpensesInRange:
    def test_no_expenses_in_range_returns_200(self, auth_client, seeded_expenses):
        """A valid range with no matching expenses must return 200."""
        # Use a date range that contains no seeded expenses (far future)
        response = auth_client.get(
            "/profile?date_from=2099-01-01&date_to=2099-12-31"
        )
        assert response.status_code == 200, (
            "Range with no matching expenses must return 200"
        )

    def test_no_expenses_in_range_shows_zero_total(self, auth_client, seeded_expenses):
        """When no expenses match the range, total spent must be ₹0.00."""
        response = auth_client.get(
            "/profile?date_from=2099-01-01&date_to=2099-12-31"
        )
        data = response.data.decode("utf-8")
        assert "₹0.00" in data, (
            "Range with no expenses must display ₹0.00 as total spent"
        )

    def test_no_expenses_in_range_shows_zero_transactions(
        self, auth_client, seeded_expenses
    ):
        """Transaction count must be 0 when no expenses match the range."""
        response = auth_client.get(
            "/profile?date_from=2099-01-01&date_to=2099-12-31"
        )
        data = response.data.decode("utf-8")
        # The transactions stat value '0' should appear in the stats section
        assert ">0<" in data or "transactions\n" in data.lower() or "0" in data, (
            "Transaction count must be 0 when no expenses match the range"
        )

    def test_no_expenses_in_range_shows_rupee_symbol(
        self, auth_client, seeded_expenses
    ):
        """₹ symbol must appear even when the total is 0.00."""
        response = auth_client.get(
            "/profile?date_from=2099-01-01&date_to=2099-12-31"
        )
        data = response.data.decode("utf-8")
        assert "₹" in data, "₹ symbol must appear even for an empty range (₹0.00)"

    def test_fresh_user_no_expenses_returns_200(self, app, client):
        """A brand-new user with zero expenses at all must get 200 on /profile."""
        from database.db import get_db as gdb

        # Create a second user with no expenses
        conn = gdb()
        conn.execute(
            "INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)",
            ("Empty User", "empty@spendly.com", generate_password_hash("pw")),
        )
        conn.commit()
        empty_user_id = conn.execute(
            "SELECT id FROM users WHERE email = ?", ("empty@spendly.com",)
        ).fetchone()["id"]
        conn.close()

        with client.session_transaction() as sess:
            sess["user_id"] = empty_user_id
            sess["user_name"] = "Empty User"

        response = client.get("/profile")
        assert response.status_code == 200, (
            "User with zero expenses must get 200 on /profile"
        )
        data = response.data.decode("utf-8")
        assert "₹0.00" in data, (
            "User with zero expenses must see ₹0.00 total"
        )


# ---------------------------------------------------------------------------
# 11. Filter bar HTML presence
# ---------------------------------------------------------------------------

class TestFilterBarPresence:
    def test_filter_bar_is_present(self, auth_client, seeded_expenses):
        """The filter bar container must be present on the profile page."""
        response = auth_client.get("/profile")
        data = response.data.decode("utf-8")
        assert "filter-bar" in data, "filter-bar element must be present in profile HTML"

    def test_all_time_preset_link_present(self, auth_client, seeded_expenses):
        """An 'All Time' preset button/link must exist in the filter bar."""
        response = auth_client.get("/profile")
        data = response.data.decode("utf-8")
        assert "All Time" in data, "'All Time' preset must appear in the filter bar"

    def test_this_month_preset_link_present(self, auth_client, seeded_expenses):
        """A 'This Month' preset button/link must exist in the filter bar."""
        response = auth_client.get("/profile")
        data = response.data.decode("utf-8")
        assert "This Month" in data, "'This Month' preset must appear in the filter bar"

    def test_last_3_months_preset_link_present(self, auth_client, seeded_expenses):
        """A 'Last 3 Months' preset button/link must exist in the filter bar."""
        response = auth_client.get("/profile")
        data = response.data.decode("utf-8")
        assert "Last 3 Months" in data, (
            "'Last 3 Months' preset must appear in the filter bar"
        )

    def test_last_6_months_preset_link_present(self, auth_client, seeded_expenses):
        """A 'Last 6 Months' preset button/link must exist in the filter bar."""
        response = auth_client.get("/profile")
        data = response.data.decode("utf-8")
        assert "Last 6 Months" in data, (
            "'Last 6 Months' preset must appear in the filter bar"
        )

    def test_date_input_fields_present(self, auth_client, seeded_expenses):
        """Two <input type='date'> fields must exist in the filter bar."""
        response = auth_client.get("/profile")
        data = response.data.decode("utf-8")
        assert 'type="date"' in data or "type='date'" in data, (
            "Date input fields must be present in the filter bar"
        )

    def test_apply_button_present(self, auth_client, seeded_expenses):
        """An Apply submit button must exist in the custom range form."""
        response = auth_client.get("/profile")
        data = response.data.decode("utf-8")
        assert "Apply" in data, "Apply submit button must be present in the filter bar"


# ---------------------------------------------------------------------------
# 12. Active preset highlighting
# ---------------------------------------------------------------------------

class TestActivePresetHighlighting:
    def test_all_time_has_active_class_when_no_filter(
        self, auth_client, seeded_expenses
    ):
        """'All Time' link must have 'active' class when no date filter is set."""
        response = auth_client.get("/profile")
        data = response.data.decode("utf-8")
        # The active class appears on the All Time link
        assert "btn-filter active" in data or "active" in data, (
            "All Time preset must be marked active when no filter is applied"
        )

    def test_this_month_has_active_class_when_active(
        self, auth_client, seeded_expenses
    ):
        """'This Month' link must have 'active' class when its params are active."""
        today = _today_str()
        first = _first_of_month(date.today())
        response = auth_client.get(f"/profile?date_from={first}&date_to={today}")
        data = response.data.decode("utf-8")
        assert "active" in data, (
            "An active class must appear when This Month filter is active"
        )

    def test_last_3_months_has_active_class_when_active(
        self, auth_client, seeded_expenses
    ):
        """'Last 3 Months' link must have 'active' class when its params are active."""
        today = _today_str()
        start = _months_ago(date.today(), 3)
        response = auth_client.get(f"/profile?date_from={start}&date_to={today}")
        data = response.data.decode("utf-8")
        assert "active" in data, (
            "An active class must appear when Last 3 Months filter is active"
        )

    def test_last_6_months_has_active_class_when_active(
        self, auth_client, seeded_expenses
    ):
        """'Last 6 Months' link must have 'active' class when its params are active."""
        today = _today_str()
        start = _months_ago(date.today(), 6)
        response = auth_client.get(f"/profile?date_from={start}&date_to={today}")
        data = response.data.decode("utf-8")
        assert "active" in data, (
            "An active class must appear when Last 6 Months filter is active"
        )


# ---------------------------------------------------------------------------
# 13. Rupee symbol — across all filter states
# ---------------------------------------------------------------------------

class TestRupeeSymbolConsistency:
    @pytest.mark.parametrize(
        "query_string",
        [
            "",
            "?date_from=&date_to=",
            "?date_from=2099-01-01&date_to=2099-12-31",
            "?date_from=2026-12-31&date_to=2026-01-01",  # inverted
            "?date_from=not-a-date",                       # malformed
        ],
    )
    def test_rupee_symbol_present_for_all_filter_states(
        self, auth_client, seeded_expenses, query_string
    ):
        """₹ must appear in the rendered page for every filter state."""
        response = auth_client.get(f"/profile{query_string}")
        assert response.status_code == 200, (
            f"Expected 200 for query '{query_string}'"
        )
        data = response.data.decode("utf-8")
        assert "₹" in data, (
            f"₹ symbol must appear on profile page for query '{query_string}'"
        )
