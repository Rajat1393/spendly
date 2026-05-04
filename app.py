import os
import sqlite3
from datetime import datetime
from flask import Flask, flash, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash
from database.db import (
    create_expense,
    create_user,
    get_category_totals,
    get_db,
    get_expense_stats,
    get_recent_expenses,
    get_top_category,
    get_user_by_email,
    get_user_by_id,
    init_db,
    seed_db,
)

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-secret-change-in-production")

EXPENSE_CATEGORIES = ["Food", "Transport", "Bills", "Health", "Entertainment", "Shopping", "Other"]


def _months_ago(dt, n):
    month = dt.month - n
    year  = dt.year + (month - 1) // 12
    month = ((month - 1) % 12) + 1
    return dt.replace(year=year, month=month, day=1)


# ------------------------------------------------------------------ #
# Routes                                                              #
# ------------------------------------------------------------------ #

@app.route("/")
def landing():
    return render_template("landing.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip()
        password = request.form.get("password", "").strip()

        if not name or not email or not password:
            flash("All fields are required.", "error")
            return render_template("register.html")

        try:
            create_user(name, email, generate_password_hash(password))
            flash("Account created! You can now sign in.", "success")
            return redirect(url_for("login"))
        except sqlite3.IntegrityError:
            flash("An account with that email address already exists.", "error")
            return render_template("register.html")

    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email", "").strip()
        password = request.form.get("password", "").strip()

        if not email or not password:
            flash("Invalid email or password.", "error")
            return render_template("login.html")

        user = get_user_by_email(email)
        if user is None or not check_password_hash(user["password_hash"], password):
            flash("Invalid email or password.", "error")
            return render_template("login.html")

        session["user_id"] = user["id"]
        session["user_name"] = user["name"]
        return redirect(url_for("profile"))

    return render_template("login.html")


# ------------------------------------------------------------------ #
# Placeholder routes — students will implement these                  #
# ------------------------------------------------------------------ #

@app.route("/terms")
def terms():
    return render_template("terms.html")


@app.route("/privacy")
def privacy():
    return render_template("privacy.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("landing"))


@app.route("/profile")
def profile():
    if not session.get("user_id"):
        return redirect(url_for("login"))

    user_row = get_user_by_id(session["user_id"])
    if user_row is None:
        session.clear()
        return redirect(url_for("login"))

    # Parse and validate date filter params
    date_from_raw = request.args.get("date_from", "").strip()
    date_to_raw   = request.args.get("date_to",   "").strip()

    date_from = None
    date_to   = None

    if date_from_raw:
        try:
            datetime.strptime(date_from_raw, "%Y-%m-%d")
            date_from = date_from_raw
        except ValueError:
            pass

    if date_to_raw:
        try:
            datetime.strptime(date_to_raw, "%Y-%m-%d")
            date_to = date_to_raw
        except ValueError:
            pass

    if date_from and date_to and date_from > date_to:
        flash("Start date must be before end date.", "error")
        date_from = None
        date_to   = None

    # Preset boundary strings passed to template for filter bar rendering
    today_dt           = datetime.today()
    today_str          = today_dt.strftime("%Y-%m-%d")
    first_of_month     = today_dt.replace(day=1).strftime("%Y-%m-%d")
    three_months_start = _months_ago(today_dt, 3).strftime("%Y-%m-%d")
    six_months_start   = _months_ago(today_dt, 6).strftime("%Y-%m-%d")

    name = user_row["name"]
    initials = "".join(part[0].upper() for part in name.split()[:2])
    member_since = datetime.strptime(
        user_row["created_at"], "%Y-%m-%d %H:%M:%S"
    ).strftime("%B %Y")

    stats_row   = get_expense_stats(session["user_id"], date_from=date_from, date_to=date_to)
    top_cat     = get_top_category(session["user_id"], date_from=date_from, date_to=date_to)
    recent_rows = get_recent_expenses(session["user_id"], limit=5, date_from=date_from, date_to=date_to)
    cat_rows    = get_category_totals(session["user_id"], date_from=date_from, date_to=date_to)

    total_spent = stats_row["total_spent"]

    user = {
        "initials":     initials,
        "name":         name,
        "email":        user_row["email"],
        "member_since": member_since,
    }
    stats = {
        "total_spent":  f"₹{total_spent:,.2f}",
        "transactions": stats_row["transaction_count"],
        "top_category": top_cat,
    }
    transactions = []
    for row in recent_rows:
        tx_date = datetime.strptime(row["date"], "%Y-%m-%d").strftime("%b %d, %Y")
        transactions.append({
            "date":        tx_date,
            "description": row["description"] or "",
            "category":    row["category"],
            "amount":      f"−₹{row['amount']:,.2f}",
            "type":        "expense",
        })

    categories = []
    for cat in cat_rows:
        percent = round(cat["total"] / total_spent * 100) if total_spent > 0 else 0
        categories.append({
            "name":    cat["name"],
            "amount":  f"₹{cat['total']:,.2f}",
            "percent": percent,
        })

    return render_template(
        "profile.html",
        user=user,
        stats=stats,
        transactions=transactions,
        categories=categories,
        date_from=date_from,
        date_to=date_to,
        today_str=today_str,
        first_of_month=first_of_month,
        three_months_start=three_months_start,
        six_months_start=six_months_start,
    )


@app.route("/analytics")
def analytics():
    if not session.get("user_id"):
        return redirect(url_for("login"))
    return render_template("analytics.html")


@app.route("/expenses/add", methods=["GET", "POST"])
def add_expense():
    if not session.get("user_id"):
        return redirect(url_for("login"))

    if request.method == "POST":
        amount_raw = request.form.get("amount", "").strip()
        category   = request.form.get("category", "").strip()
        date_raw   = request.form.get("date", "").strip()
        desc_raw   = request.form.get("description", "").strip()

        error = None
        amount = None

        try:
            amount = float(amount_raw)
            if amount <= 0:
                raise ValueError
        except ValueError:
            error = "Amount must be a positive number."

        if not error and category not in EXPENSE_CATEGORIES:
            error = "Please select a valid category."

        if not error:
            try:
                datetime.strptime(date_raw, "%Y-%m-%d")
            except ValueError:
                error = "Please enter a valid date."

        if not error and len(desc_raw) > 200:
            error = "Description must be 200 characters or fewer."

        if error:
            flash(error, "error")
            form_values = {
                "amount":      amount_raw,
                "category":    category,
                "date":        date_raw,
                "description": desc_raw,
            }
            return render_template("add_expense.html", categories=EXPENSE_CATEGORIES, form=form_values)

        description = desc_raw or None
        create_expense(session["user_id"], amount, category, date_raw, description)
        flash("Expense added.", "success")
        return redirect(url_for("profile"))

    today = datetime.today().strftime("%Y-%m-%d")
    return render_template(
        "add_expense.html",
        categories=EXPENSE_CATEGORIES,
        form={"date": today},
    )


@app.route("/expenses/<int:id>/edit")
def edit_expense(id):
    return "Edit expense — coming in Step 8"


@app.route("/expenses/<int:id>/delete")
def delete_expense(id):
    return "Delete expense — coming in Step 9"


if __name__ == "__main__":
    with app.app_context():
        init_db()
        seed_db()
    app.run(debug=os.environ.get("FLASK_DEBUG", "false").lower() == "true", port=5001)
