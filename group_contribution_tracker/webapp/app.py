"""Contribution ledger: a public read-only page plus a password-protected
manager area for at most two managers.

Run locally:
    pip install -r requirements.txt
    flask --app app run

Everything the app stores lives in DATA_DIR (default: ./data next to this file):
    ledger.sqlite3   the database
    secret_key.txt   the cookie-signing key, generated on first run
"""
from __future__ import annotations

import csv
import io
import os
import secrets
import sqlite3
import time
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from functools import wraps

from flask import (Flask, abort, flash, g, redirect, render_template, request,
                   Response, session, url_for)
from werkzeug.security import check_password_hash, generate_password_hash

MAX_MANAGERS = 2
LOGIN_WINDOW_SECONDS = 15 * 60
LOGIN_MAX_FAILURES = 8

CURRENCY_SYMBOLS = {
    "GHS": "GH₵", "USD": "$", "GBP": "£", "EUR": "€", "NGN": "₦",
    "KES": "KSh", "ZAR": "R", "CAD": "CA$", "AUD": "A$",
}

SCHEMA = """
CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS managers (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    username      TEXT NOT NULL UNIQUE,
    display_name  TEXT NOT NULL,
    password_hash TEXT NOT NULL,
    created_at    TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS contributions (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    name         TEXT NOT NULL,
    amount_cents INTEGER NOT NULL CHECK (amount_cents > 0),
    paid_on      TEXT NOT NULL,
    note         TEXT NOT NULL DEFAULT '',
    created_at   TEXT NOT NULL,
    created_by   TEXT NOT NULL,
    updated_at   TEXT NOT NULL,
    updated_by   TEXT NOT NULL
);
"""

DEFAULT_SETTINGS = {
    "group_name": "Funeral Contribution For Our Brother Emmanuel Papa Nii Quaye",
    "description": ("Contributions from the group towards the funeral of our brother "
                    "Emmanuel Papa Nii Quaye. Every amount received is recorded here by "
                    "the managers so that all members can see it."),
    "currency": "GHS",
    "goal_cents": "",
}


# --------------------------------------------------------------------------
# app factory
# --------------------------------------------------------------------------
def create_app(test_config: dict | None = None) -> Flask:
    app = Flask(__name__, instance_relative_config=False)

    data_dir = os.environ.get("DATA_DIR") or os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
    app.config.update(
        DATA_DIR=data_dir,
        DATABASE=os.path.join(data_dir, "ledger.sqlite3"),
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=os.environ.get("COOKIE_SECURE", "1") == "1",
        PERMANENT_SESSION_LIFETIME=60 * 60 * 12,
        MAX_CONTENT_LENGTH=64 * 1024,
    )
    if test_config:
        app.config.update(test_config)

    os.makedirs(app.config["DATA_DIR"], exist_ok=True)
    app.secret_key = _load_secret_key(app)
    app.login_failures = {}  # username -> timestamps of recent failed sign-ins

    with app.app_context():
        init_db()

    app.teardown_appcontext(_close_db)
    app.before_request(_csrf_protect)
    app.context_processor(_template_globals)
    _register_routes(app)
    _register_cli(app)
    return app


def _load_secret_key(app: Flask) -> str:
    key = os.environ.get("SECRET_KEY")
    if key:
        return key
    path = os.path.join(app.config["DATA_DIR"], "secret_key.txt")
    if os.path.exists(path):
        with open(path, encoding="utf-8") as fh:
            key = fh.read().strip()
            if key:
                return key
    key = secrets.token_urlsafe(48)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(key)
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass
    return key


# --------------------------------------------------------------------------
# database helpers
# --------------------------------------------------------------------------
def get_db() -> sqlite3.Connection:
    from flask import current_app
    if "db" not in g:
        g.db = sqlite3.connect(current_app.config["DATABASE"], detect_types=sqlite3.PARSE_DECLTYPES)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


def _close_db(_exc=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    db = get_db()
    db.executescript(SCHEMA)
    for key, value in DEFAULT_SETTINGS.items():
        db.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", (key, value))
    db.commit()


def get_settings() -> dict:
    rows = get_db().execute("SELECT key, value FROM settings").fetchall()
    s = {r["key"]: r["value"] for r in rows}
    s["goal_cents"] = int(s["goal_cents"]) if s.get("goal_cents") else None
    return s


def set_setting(key: str, value: str):
    get_db().execute("INSERT INTO settings (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value", (key, value))


def manager_count() -> int:
    return get_db().execute("SELECT COUNT(*) FROM managers").fetchone()[0]


def list_managers() -> list[sqlite3.Row]:
    return get_db().execute("SELECT id, username, display_name, created_at FROM managers ORDER BY id").fetchall()


def create_manager(username: str, display_name: str, password: str) -> int:
    """Create a manager. Raises ValueError with a message the UI can show."""
    username = username.strip().lower()
    display_name = " ".join(display_name.split())
    if not (3 <= len(username) <= 30) or not username.replace(".", "").replace("_", "").isalnum():
        raise ValueError("Username must be 3 to 30 letters, digits, dots or underscores.")
    if not display_name:
        raise ValueError("Enter the manager's name as members should see it.")
    if len(password) < 8:
        raise ValueError("Password must be at least 8 characters.")
    db = get_db()
    if manager_count() >= MAX_MANAGERS:
        raise ValueError(f"The ledger allows at most {MAX_MANAGERS} managers.")
    if db.execute("SELECT 1 FROM managers WHERE username = ?", (username,)).fetchone():
        raise ValueError("That username is already taken.")
    cur = db.execute(
        "INSERT INTO managers (username, display_name, password_hash, created_at) VALUES (?, ?, ?, ?)",
        (username, display_name, generate_password_hash(password), now_iso()),
    )
    db.commit()
    return cur.lastrowid


def set_manager_password(manager_id: int, password: str):
    if len(password) < 8:
        raise ValueError("Password must be at least 8 characters.")
    db = get_db()
    db.execute("UPDATE managers SET password_hash = ? WHERE id = ?", (generate_password_hash(password), manager_id))
    db.commit()


# --------------------------------------------------------------------------
# money and dates
# --------------------------------------------------------------------------
def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def parse_amount(text: str) -> int:
    """'150', '150.5', '1,250.00' -> cents. Raises ValueError."""
    cleaned = (text or "").replace(",", "").replace(" ", "").strip()
    try:
        value = Decimal(cleaned)
    except InvalidOperation:
        raise ValueError("Enter the amount as a number, for example 150 or 150.50.")
    if value <= 0:
        raise ValueError("The amount must be more than zero.")
    if value > Decimal("1000000000"):
        raise ValueError("That amount is too large.")
    return int((value * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def parse_date(text: str) -> str:
    try:
        return date.fromisoformat((text or "").strip()).isoformat()
    except ValueError:
        raise ValueError("Pick the date the money was received.")


def money(cents: int | None, currency: str) -> str:
    if cents is None:
        return ""
    symbol = CURRENCY_SYMBOLS.get(currency)
    body = f"{cents / 100:,.2f}"
    return f"{symbol}{body}" if symbol else f"{currency} {body}"


def nice_date(iso: str) -> str:
    try:
        return date.fromisoformat(iso).strftime("%-d %b %Y")
    except ValueError:
        return iso


def nice_stamp(iso: str | None) -> str:
    if not iso:
        return "never"
    try:
        return datetime.fromisoformat(iso).strftime("%-d %b %Y, %H:%M UTC")
    except ValueError:
        return iso


# --------------------------------------------------------------------------
# auth helpers
# --------------------------------------------------------------------------
def current_manager() -> sqlite3.Row | None:
    mid = session.get("manager_id")
    if not mid:
        return None
    return get_db().execute("SELECT id, username, display_name FROM managers WHERE id = ?", (mid,)).fetchone()


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if manager_count() == 0:
            return redirect(url_for("setup"))
        if current_manager() is None:
            session.clear()
            return redirect(url_for("login", next=request.path))
        return view(*args, **kwargs)
    return wrapped


def _csrf_protect():
    if request.method == "POST":
        token = session.get("csrf")
        sent = request.form.get("csrf")
        if not token or not sent or not secrets.compare_digest(token, sent):
            abort(400, "The form expired. Go back, reload the page and try again.")


def csrf_token() -> str:
    if "csrf" not in session:
        session["csrf"] = secrets.token_urlsafe(32)
    return session["csrf"]


def _too_many_failures(app: Flask, username: str) -> bool:
    now = time.time()
    hits = [t for t in app.login_failures.get(username, []) if now - t < LOGIN_WINDOW_SECONDS]
    app.login_failures[username] = hits
    return len(hits) >= LOGIN_MAX_FAILURES


def _record_failure(app: Flask, username: str):
    app.login_failures.setdefault(username, []).append(time.time())


def _template_globals():
    return {
        "csrf_token": csrf_token,
        "money": money,
        "nice_date": nice_date,
        "nice_stamp": nice_stamp,
        "manager": current_manager() if "manager_id" in session else None,
    }


# --------------------------------------------------------------------------
# ledger queries
# --------------------------------------------------------------------------
def ledger_summary(q: str = "") -> dict:
    db = get_db()
    like = f"%{q.strip().lower()}%" if q.strip() else None
    where = "WHERE lower(name) LIKE ?" if like else ""
    params = (like,) if like else ()

    totals = db.execute(
        f"SELECT COALESCE(SUM(amount_cents), 0) AS total, COUNT(*) AS entries, "
        f"COUNT(DISTINCT lower(trim(name))) AS members, MAX(updated_at) AS updated "
        f"FROM contributions {where}", params).fetchone()
    members = db.execute(
        f"SELECT min(name) AS name, SUM(amount_cents) AS total, COUNT(*) AS payments, MAX(paid_on) AS last_paid "
        f"FROM contributions {where} GROUP BY lower(trim(name)) ORDER BY total DESC, name COLLATE NOCASE", params).fetchall()
    entries = db.execute(
        f"SELECT * FROM contributions {where} ORDER BY paid_on DESC, id DESC", params).fetchall()
    return {"totals": totals, "members": members, "entries": entries}


# --------------------------------------------------------------------------
# routes
# --------------------------------------------------------------------------
def _register_routes(app: Flask):

    @app.get("/")
    def public():
        s = get_settings()
        q = request.args.get("q", "")
        view = "entries" if request.args.get("view") == "entries" else "members"
        data = ledger_summary(q)
        overall = get_db().execute("SELECT COALESCE(SUM(amount_cents),0) AS total, MAX(updated_at) AS updated FROM contributions").fetchone()
        goal = s["goal_cents"]
        pct = min(100, round(overall["total"] * 100 / goal)) if goal else None
        return render_template("public.html", s=s, q=q, view=view, data=data, overall=overall,
                               pct=pct, managers=list_managers())

    @app.get("/export.csv")
    def export_csv():
        s = get_settings()
        rows = get_db().execute("SELECT paid_on, name, amount_cents, note FROM contributions ORDER BY paid_on, id").fetchall()
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(["Date", "Member", "Amount", "Currency", "Note"])
        for r in rows:
            w.writerow([r["paid_on"], r["name"], f"{r['amount_cents'] / 100:.2f}", s["currency"], r["note"]])
        fname = "".join(c if c.isalnum() or c in " -" else "" for c in s["group_name"]).strip().replace(" ", "-").lower() or "ledger"
        return Response(buf.getvalue(), mimetype="text/csv",
                        headers={"Content-Disposition": f'attachment; filename="{fname}-contributions.csv"'})

    # ---- first-run setup ----
    @app.route("/manage/setup", methods=["GET", "POST"])
    def setup():
        if manager_count() > 0:
            return redirect(url_for("login"))
        error = None
        if request.method == "POST":
            try:
                mid = create_manager(request.form.get("username", ""), request.form.get("display_name", ""), request.form.get("password", ""))
                session.clear()
                session.permanent = True
                session["manager_id"] = mid
                flash("Welcome. Your manager account is ready.")
                return redirect(url_for("manage"))
            except ValueError as e:
                error = str(e)
        return render_template("setup.html", error=error, form=request.form)

    # ---- login / logout ----
    @app.route("/manage/login", methods=["GET", "POST"])
    def login():
        if manager_count() == 0:
            return redirect(url_for("setup"))
        error = None
        if request.method == "POST":
            username = request.form.get("username", "").strip().lower()
            password = request.form.get("password", "")
            if _too_many_failures(app, username):
                error = "Too many failed attempts. Wait 15 minutes and try again."
            else:
                row = get_db().execute("SELECT id, password_hash FROM managers WHERE username = ?", (username,)).fetchone()
                if row and check_password_hash(row["password_hash"], password):
                    session.clear()
                    session.permanent = True
                    session["manager_id"] = row["id"]
                    nxt = request.args.get("next", "")
                    return redirect(nxt if nxt.startswith("/manage") else url_for("manage"))
                _record_failure(app, username)
                error = "Wrong username or password."
        return render_template("login.html", error=error)

    @app.post("/manage/logout")
    @login_required
    def logout():
        session.clear()
        flash("You are signed out.")
        return redirect(url_for("public"))

    # ---- manager dashboard ----
    @app.get("/manage")
    @login_required
    def manage():
        s = get_settings()
        q = request.args.get("q", "")
        data = ledger_summary(q)
        return render_template("manage.html", s=s, q=q, data=data, today=date.today().isoformat())

    def _entry_from_form() -> dict:
        name = " ".join(request.form.get("name", "").split())
        if not name or len(name) > 80:
            raise ValueError("Enter the member's name.")
        return {
            "name": name,
            "amount_cents": parse_amount(request.form.get("amount", "")),
            "paid_on": parse_date(request.form.get("paid_on", "")),
            "note": " ".join(request.form.get("note", "").split())[:120],
        }

    @app.post("/manage/entry")
    @login_required
    def add_entry():
        m = current_manager()
        try:
            e = _entry_from_form()
        except ValueError as err:
            flash(str(err), "error")
            return redirect(url_for("manage"))
        db = get_db()
        stamp = now_iso()
        db.execute("INSERT INTO contributions (name, amount_cents, paid_on, note, created_at, created_by, updated_at, updated_by) VALUES (?,?,?,?,?,?,?,?)",
                   (e["name"], e["amount_cents"], e["paid_on"], e["note"], stamp, m["username"], stamp, m["username"]))
        db.commit()
        flash(f"Recorded {e['name']}, {money(e['amount_cents'], get_settings()['currency'])}.")
        return redirect(url_for("manage"))

    @app.route("/manage/entry/<int:entry_id>/edit", methods=["GET", "POST"])
    @login_required
    def edit_entry(entry_id: int):
        db = get_db()
        row = db.execute("SELECT * FROM contributions WHERE id = ?", (entry_id,)).fetchone()
        if row is None:
            abort(404)
        error = None
        if request.method == "POST":
            try:
                e = _entry_from_form()
                db.execute("UPDATE contributions SET name=?, amount_cents=?, paid_on=?, note=?, updated_at=?, updated_by=? WHERE id=?",
                           (e["name"], e["amount_cents"], e["paid_on"], e["note"], now_iso(), current_manager()["username"], entry_id))
                db.commit()
                flash("Entry updated.")
                return redirect(url_for("manage"))
            except ValueError as err:
                error = str(err)
        return render_template("entry_form.html", row=row, error=error, s=get_settings())

    @app.post("/manage/entry/<int:entry_id>/delete")
    @login_required
    def delete_entry(entry_id: int):
        db = get_db()
        row = db.execute("SELECT name, amount_cents FROM contributions WHERE id = ?", (entry_id,)).fetchone()
        if row is None:
            abort(404)
        db.execute("DELETE FROM contributions WHERE id = ?", (entry_id,))
        db.commit()
        flash(f"Removed {row['name']}, {money(row['amount_cents'], get_settings()['currency'])}.")
        return redirect(url_for("manage"))

    # ---- settings ----
    @app.route("/manage/settings", methods=["GET", "POST"])
    @login_required
    def settings():
        s = get_settings()
        error = None
        if request.method == "POST":
            name = " ".join(request.form.get("group_name", "").split())[:120]
            currency = request.form.get("currency", "").strip().upper()
            goal_text = request.form.get("goal", "").strip()
            if not name:
                error = "Enter the group name."
            elif not (len(currency) == 3 and currency.isalpha()):
                error = "Currency must be a 3-letter code such as GHS, USD or GBP."
            else:
                try:
                    goal = parse_amount(goal_text) if goal_text else None
                    set_setting("group_name", name)
                    set_setting("currency", currency)
                    set_setting("description", " ".join(request.form.get("description", "").split())[:400])
                    set_setting("goal_cents", str(goal) if goal else "")
                    get_db().commit()
                    flash("Settings saved.")
                    return redirect(url_for("manage"))
                except ValueError as err:
                    error = str(err)
            s = dict(s, group_name=name, currency=currency, description=request.form.get("description", ""),
                     goal_cents=None)
        return render_template("settings.html", s=s, error=error, goal_text=request.form.get("goal", "") if request.method == "POST" else ("" if not s["goal_cents"] else f"{s['goal_cents'] / 100:.2f}"))

    # ---- managers ----
    @app.route("/manage/managers", methods=["GET", "POST"])
    @login_required
    def managers():
        error = None
        if request.method == "POST":
            try:
                create_manager(request.form.get("username", ""), request.form.get("display_name", ""), request.form.get("password", ""))
                flash("Manager added. Give them their username and password privately.")
                return redirect(url_for("managers"))
            except ValueError as e:
                error = str(e)
        return render_template("managers.html", managers=list_managers(), error=error, max_managers=MAX_MANAGERS, form=request.form)

    @app.post("/manage/managers/<int:manager_id>/remove")
    @login_required
    def remove_manager(manager_id: int):
        me = current_manager()
        if manager_id == me["id"]:
            flash("You cannot remove your own account. Ask the other manager to do it.", "error")
            return redirect(url_for("managers"))
        db = get_db()
        db.execute("DELETE FROM managers WHERE id = ?", (manager_id,))
        db.commit()
        flash("Manager removed.")
        return redirect(url_for("managers"))

    @app.route("/manage/password", methods=["GET", "POST"])
    @login_required
    def password():
        error = None
        if request.method == "POST":
            me = current_manager()
            row = get_db().execute("SELECT password_hash FROM managers WHERE id = ?", (me["id"],)).fetchone()
            if not check_password_hash(row["password_hash"], request.form.get("current", "")):
                error = "Your current password is wrong."
            elif request.form.get("new", "") != request.form.get("confirm", ""):
                error = "The two new passwords do not match."
            else:
                try:
                    set_manager_password(me["id"], request.form.get("new", ""))
                    flash("Password changed.")
                    return redirect(url_for("manage"))
                except ValueError as e:
                    error = str(e)
        return render_template("password.html", error=error)

    @app.errorhandler(404)
    def not_found(_e):
        return render_template("error.html", code=404, message="That page does not exist."), 404

    @app.errorhandler(400)
    def bad_request(e):
        return render_template("error.html", code=400, message=getattr(e, "description", "Bad request.")), 400


# --------------------------------------------------------------------------
# command line helpers (recovery when a manager is locked out)
# --------------------------------------------------------------------------
def _register_cli(app: Flask):
    import click

    @app.cli.command("add-manager")
    @click.argument("username")
    @click.argument("display_name")
    @click.password_option()
    def cli_add_manager(username, display_name, password):
        """Create a manager account (at most two)."""
        try:
            create_manager(username, display_name, password)
            click.echo(f"Manager '{username}' created.")
        except ValueError as e:
            raise click.ClickException(str(e))

    @app.cli.command("reset-password")
    @click.argument("username")
    @click.password_option()
    def cli_reset_password(username, password):
        """Set a new password for a manager who is locked out."""
        row = get_db().execute("SELECT id FROM managers WHERE username = ?", (username.strip().lower(),)).fetchone()
        if row is None:
            raise click.ClickException("No manager with that username.")
        try:
            set_manager_password(row["id"], password)
            click.echo("Password updated.")
        except ValueError as e:
            raise click.ClickException(str(e))

    @app.cli.command("list-managers")
    def cli_list_managers():
        """Show the manager accounts."""
        for m in list_managers():
            click.echo(f"{m['username']}\t{m['display_name']}\tsince {m['created_at']}")

