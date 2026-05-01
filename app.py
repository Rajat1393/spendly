import os
import sqlite3
from flask import Flask, flash, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash
from database.db import create_user, get_db, get_user_by_email, init_db, seed_db

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-secret-change-in-production")


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

    name = session["user_name"]
    initials = "".join(part[0].upper() for part in name.split()[:2])
    user = {
        "name": name,
        "email": "priya@example.com",
        "initials": initials,
        "member_since": "January 2024"
    }
    stats = {
        "total_spent": "₹24,850",
        "transactions": 47,
        "top_category": "Food & Dining"
    }
    transactions = [
        {"date": "Apr 28, 2026", "description": "Swiggy Order",         "category": "Food & Dining",  "amount": "−₹420",   "type": "expense"},
        {"date": "Apr 26, 2026", "description": "Metro Card Recharge",  "category": "Transport",       "amount": "−₹200",   "type": "expense"},
        {"date": "Apr 25, 2026", "description": "Netflix Subscription", "category": "Entertainment",   "amount": "−₹649",   "type": "expense"},
        {"date": "Apr 24, 2026", "description": "Electricity Bill",     "category": "Utilities",       "amount": "−₹1,340", "type": "expense"},
        {"date": "Apr 22, 2026", "description": "Grocery Store",        "category": "Food & Dining",   "amount": "−₹870",   "type": "expense"},
    ]
    categories = [
        {"name": "Food & Dining",  "amount": "₹8,240", "percent": 33},
        {"name": "Utilities",      "amount": "₹5,180", "percent": 21},
        {"name": "Transport",      "amount": "₹3,920", "percent": 16},
        {"name": "Entertainment",  "amount": "₹3,260", "percent": 13},
        {"name": "Shopping",       "amount": "₹4,250", "percent": 17},
    ]
    return render_template("profile.html", user=user, stats=stats,
                           transactions=transactions, categories=categories)


@app.route("/expenses/add")
def add_expense():
    return "Add expense — coming in Step 7"


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
    app.run(debug=True, port=5001)
