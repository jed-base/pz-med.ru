from __future__ import annotations

import csv
import hmac
import io
import os
import secrets
import sqlite3
import time
from datetime import date, datetime, timedelta
from functools import wraps
from pathlib import Path

from flask import (
    Flask,
    Response,
    abort,
    flash,
    g,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from werkzeug.middleware.proxy_fix import ProxyFix
from werkzeug.security import check_password_hash, generate_password_hash


OFFICE_PREFIX = "/office"
DB_PATH = Path(os.environ.get("OFFICE_DB_PATH", "/var/lib/pz-med-office/office.sqlite3"))
OFFICE_USERNAME = os.environ.get("OFFICE_USERNAME", "admin").strip() or "admin"
INITIAL_PASSWORD_HASH = os.environ.get("OFFICE_PASSWORD_HASH", "").strip()
SECRET_KEY = os.environ.get("SECRET_KEY", "").strip()

if not SECRET_KEY:
    raise RuntimeError("SECRET_KEY is required for PZ-Med office")
if not INITIAL_PASSWORD_HASH:
    raise RuntimeError("OFFICE_PASSWORD_HASH is required for PZ-Med office")


app = Flask(
    __name__,
    template_folder="templates",
    static_folder="static",
    static_url_path=f"{OFFICE_PREFIX}/static",
)
app.secret_key = SECRET_KEY
app.config.update(
    SESSION_COOKIE_NAME="pz_med_office_session",
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SECURE=True,
    SESSION_COOKIE_SAMESITE="Strict",
    SESSION_COOKIE_PATH=OFFICE_PREFIX,
    PERMANENT_SESSION_LIFETIME=timedelta(hours=8),
    MAX_CONTENT_LENGTH=128 * 1024,
)
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

_LOGIN_ATTEMPTS: dict[str, list[float]] = {}
_LOGIN_WINDOW_SECONDS = 15 * 60
_LOGIN_MAX_FAILURES = 5


def _now_iso() -> str:
    return datetime.now().replace(microsecond=0).isoformat(sep=" ")


def _connect_db() -> sqlite3.Connection:
    connection = sqlite3.connect(DB_PATH, timeout=10)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA journal_mode = WAL")
    connection.execute("PRAGMA busy_timeout = 10000")
    return connection


def get_db() -> sqlite3.Connection:
    if "db" not in g:
        g.db = _connect_db()
    return g.db


@app.teardown_appcontext
def _close_db(_error=None) -> None:
    connection = g.pop("db", None)
    if connection is not None:
        connection.close()


def init_db() -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    connection = _connect_db()
    try:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS customers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                org_type TEXT NOT NULL DEFAULT 'state'
                    CHECK (org_type IN ('state', 'private')),
                inn TEXT,
                contract_number TEXT,
                contract_date TEXT,
                support_until TEXT,
                it_contact TEXT,
                notes TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS deployments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                customer_id INTEGER NOT NULL,
                kind TEXT NOT NULL CHECK (kind IN ('initial', 'update')),
                version TEXT NOT NULL,
                installed_on TEXT NOT NULL,
                installation_id TEXT,
                build_commit TEXT,
                sha256 TEXT,
                notes TEXT,
                created_at TEXT NOT NULL,
                FOREIGN KEY (customer_id) REFERENCES customers(id) ON DELETE CASCADE
            );

            CREATE INDEX IF NOT EXISTS ix_deployments_customer_date
                ON deployments(customer_id, installed_on DESC, id DESC);
            """
        )
        connection.execute(
            "INSERT OR IGNORE INTO settings(key, value, updated_at) VALUES (?, ?, ?)",
            ("admin_password_hash", INITIAL_PASSWORD_HASH, _now_iso()),
        )
        connection.commit()
    finally:
        connection.close()


def _setting(key: str) -> str | None:
    row = get_db().execute(
        "SELECT value FROM settings WHERE key = ?", (key,)
    ).fetchone()
    return row["value"] if row else None


def _set_setting(key: str, value: str) -> None:
    get_db().execute(
        """
        INSERT INTO settings(key, value, updated_at)
        VALUES (?, ?, ?)
        ON CONFLICT(key) DO UPDATE SET
            value = excluded.value,
            updated_at = excluded.updated_at
        """,
        (key, value, _now_iso()),
    )
    get_db().commit()


def _csrf_token() -> str:
    token = session.get("csrf_token")
    if not token:
        token = secrets.token_urlsafe(32)
        session["csrf_token"] = token
    return token


def _validate_csrf() -> None:
    expected = session.get("csrf_token", "")
    supplied = request.form.get("csrf_token", "") or request.headers.get("X-CSRF-Token", "")
    if not expected or not supplied or not hmac.compare_digest(expected, supplied):
        abort(400, "Некорректный CSRF-токен")


@app.before_request
def _before_request() -> None:
    if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
        _validate_csrf()


@app.after_request
def _security_headers(response: Response) -> Response:
    response.headers["X-Robots-Tag"] = "noindex, nofollow, noarchive"
    response.headers["Cache-Control"] = "no-store"
    response.headers["Pragma"] = "no-cache"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; style-src 'self'; img-src 'self' data:; "
        "form-action 'self'; frame-ancestors 'none'; base-uri 'self'"
    )
    return response


@app.context_processor
def _template_context():
    return {
        "csrf_token": _csrf_token,
        "office_username": OFFICE_USERNAME,
        "support_badge": _support_badge,
        "fmt_date": _fmt_date,
    }


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("office_authenticated"):
            return redirect(url_for("login", next=request.path))
        return view(*args, **kwargs)

    return wrapped


def _client_key() -> str:
    return request.remote_addr or "unknown"


def _prune_attempts(key: str) -> list[float]:
    now = time.monotonic()
    attempts = [
        timestamp
        for timestamp in _LOGIN_ATTEMPTS.get(key, [])
        if now - timestamp < _LOGIN_WINDOW_SECONDS
    ]
    if attempts:
        _LOGIN_ATTEMPTS[key] = attempts
    else:
        _LOGIN_ATTEMPTS.pop(key, None)
    return attempts


def _register_failed_login(key: str) -> None:
    attempts = _prune_attempts(key)
    attempts.append(time.monotonic())
    _LOGIN_ATTEMPTS[key] = attempts


def _validate_date(value: str | None, field_name: str, *, required: bool = False) -> str | None:
    value = (value or "").strip()
    if not value:
        if required:
            raise ValueError(f"Заполните поле «{field_name}».")
        return None
    try:
        date.fromisoformat(value)
    except ValueError as error:
        raise ValueError(f"Некорректная дата в поле «{field_name}».") from error
    return value


def _fmt_date(value: str | None) -> str:
    if not value:
        return "—"
    try:
        return date.fromisoformat(value).strftime("%d.%m.%Y")
    except ValueError:
        return value


def _support_badge(value: str | None) -> tuple[str, str]:
    if not value:
        return ("Не указано", "neutral")
    try:
        until = date.fromisoformat(value)
    except ValueError:
        return (value, "neutral")
    today = date.today()
    if until < today:
        return (f"Истекла {until.strftime('%d.%m.%Y')}", "expired")
    if (until - today).days <= 30:
        return (f"До {until.strftime('%d.%m.%Y')}", "warning")
    return (f"До {until.strftime('%d.%m.%Y')}", "active")


def _customer_or_404(customer_id: int) -> sqlite3.Row:
    row = get_db().execute(
        "SELECT * FROM customers WHERE id = ?", (customer_id,)
    ).fetchone()
    if row is None:
        abort(404)
    return row


def _deployment_or_404(deployment_id: int) -> sqlite3.Row:
    row = get_db().execute(
        "SELECT * FROM deployments WHERE id = ?", (deployment_id,)
    ).fetchone()
    if row is None:
        abort(404)
    return row


@app.route(f"{OFFICE_PREFIX}/login", methods=["GET", "POST"])
def login():
    if session.get("office_authenticated"):
        return redirect(url_for("dashboard"))

    key = _client_key()
    attempts = _prune_attempts(key)
    blocked = len(attempts) >= _LOGIN_MAX_FAILURES

    if request.method == "POST":
        if blocked:
            flash("Слишком много попыток входа. Повторите через 15 минут.", "error")
            return render_template("login.html", blocked=True), 429

        username = (request.form.get("username") or "").strip()
        password = request.form.get("password") or ""
        password_hash = _setting("admin_password_hash") or INITIAL_PASSWORD_HASH

        if username == OFFICE_USERNAME and check_password_hash(password_hash, password):
            _LOGIN_ATTEMPTS.pop(key, None)
            session.clear()
            session["office_authenticated"] = True
            session["csrf_token"] = secrets.token_urlsafe(32)
            session.permanent = True
            destination = request.args.get("next", "")
            if not destination.startswith(f"{OFFICE_PREFIX}/"):
                destination = url_for("dashboard")
            return redirect(destination)

        _register_failed_login(key)
        flash("Неверный логин или пароль.", "error")

    return render_template("login.html", blocked=blocked)


@app.post(f"{OFFICE_PREFIX}/logout")
@login_required
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.get(f"{OFFICE_PREFIX}/")
@login_required
def dashboard():
    search = (request.args.get("q") or "").strip()
    like = f"%{search}%"
    rows = get_db().execute(
        """
        SELECT
            c.*,
            (SELECT d.version FROM deployments d
             WHERE d.customer_id = c.id
             ORDER BY d.installed_on DESC, d.id DESC LIMIT 1) AS current_version,
            (SELECT d.installed_on FROM deployments d
             WHERE d.customer_id = c.id
             ORDER BY d.installed_on DESC, d.id DESC LIMIT 1) AS current_installed_on,
            (SELECT d.installation_id FROM deployments d
             WHERE d.customer_id = c.id AND COALESCE(d.installation_id, '') <> ''
             ORDER BY d.installed_on DESC, d.id DESC LIMIT 1) AS installation_id,
            (SELECT d.version FROM deployments d
             WHERE d.customer_id = c.id AND d.kind = 'initial'
             ORDER BY d.installed_on ASC, d.id ASC LIMIT 1) AS initial_version,
            (SELECT d.installed_on FROM deployments d
             WHERE d.customer_id = c.id AND d.kind = 'initial'
             ORDER BY d.installed_on ASC, d.id ASC LIMIT 1) AS initial_installed_on,
            (SELECT d.installed_on FROM deployments d
             WHERE d.customer_id = c.id AND d.kind = 'update'
             ORDER BY d.installed_on DESC, d.id DESC LIMIT 1) AS last_update_on,
            (SELECT COUNT(*) FROM deployments d
             WHERE d.customer_id = c.id AND d.kind = 'update') AS update_count
        FROM customers c
        WHERE (? = '' OR c.name LIKE ? OR COALESCE(c.inn, '') LIKE ?
               OR COALESCE(c.contract_number, '') LIKE ?)
        ORDER BY c.name COLLATE NOCASE
        """,
        (search, like, like, like),
    ).fetchall()

    total_customers = get_db().execute("SELECT COUNT(*) AS n FROM customers").fetchone()["n"]
    total_updates = get_db().execute(
        "SELECT COUNT(*) AS n FROM deployments WHERE kind = 'update'"
    ).fetchone()["n"]
    today = date.today().isoformat()
    active_support = get_db().execute(
        "SELECT COUNT(*) AS n FROM customers WHERE support_until >= ?", (today,)
    ).fetchone()["n"]

    return render_template(
        "dashboard.html",
        customers=rows,
        search=search,
        total_customers=total_customers,
        total_updates=total_updates,
        active_support=active_support,
    )


@app.route(f"{OFFICE_PREFIX}/customers/new", methods=["GET", "POST"])
@login_required
def customer_new():
    if request.method == "POST":
        try:
            name = (request.form.get("name") or "").strip()
            if not name:
                raise ValueError("Укажите наименование организации.")
            org_type = (request.form.get("org_type") or "state").strip()
            if org_type not in {"state", "private"}:
                raise ValueError("Некорректный тип организации.")
            contract_date = _validate_date(request.form.get("contract_date"), "Дата договора")
            support_until = _validate_date(request.form.get("support_until"), "Поддержка до")
            now = _now_iso()
            cursor = get_db().execute(
                """
                INSERT INTO customers(
                    name, org_type, inn, contract_number, contract_date,
                    support_until, it_contact, notes, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    name,
                    org_type,
                    (request.form.get("inn") or "").strip() or None,
                    (request.form.get("contract_number") or "").strip() or None,
                    contract_date,
                    support_until,
                    (request.form.get("it_contact") or "").strip() or None,
                    (request.form.get("notes") or "").strip() or None,
                    now,
                    now,
                ),
            )
            get_db().commit()
            flash("Заказчик добавлен. Теперь можно зафиксировать первую поставку.", "success")
            return redirect(url_for("customer_detail", customer_id=cursor.lastrowid))
        except ValueError as error:
            flash(str(error), "error")

    return render_template("customer_form.html", customer=None)


@app.get(f"{OFFICE_PREFIX}/customers/<int:customer_id>")
@login_required
def customer_detail(customer_id: int):
    customer = _customer_or_404(customer_id)
    deployments = get_db().execute(
        """
        SELECT * FROM deployments
        WHERE customer_id = ?
        ORDER BY installed_on DESC, id DESC
        """,
        (customer_id,),
    ).fetchall()
    return render_template(
        "customer_detail.html",
        customer=customer,
        deployments=deployments,
    )


@app.route(f"{OFFICE_PREFIX}/customers/<int:customer_id>/edit", methods=["GET", "POST"])
@login_required
def customer_edit(customer_id: int):
    customer = _customer_or_404(customer_id)
    if request.method == "POST":
        try:
            name = (request.form.get("name") or "").strip()
            if not name:
                raise ValueError("Укажите наименование организации.")
            org_type = (request.form.get("org_type") or "state").strip()
            if org_type not in {"state", "private"}:
                raise ValueError("Некорректный тип организации.")
            contract_date = _validate_date(request.form.get("contract_date"), "Дата договора")
            support_until = _validate_date(request.form.get("support_until"), "Поддержка до")
            get_db().execute(
                """
                UPDATE customers SET
                    name = ?, org_type = ?, inn = ?, contract_number = ?,
                    contract_date = ?, support_until = ?, it_contact = ?,
                    notes = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    name,
                    org_type,
                    (request.form.get("inn") or "").strip() or None,
                    (request.form.get("contract_number") or "").strip() or None,
                    contract_date,
                    support_until,
                    (request.form.get("it_contact") or "").strip() or None,
                    (request.form.get("notes") or "").strip() or None,
                    _now_iso(),
                    customer_id,
                ),
            )
            get_db().commit()
            flash("Данные заказчика сохранены.", "success")
            return redirect(url_for("customer_detail", customer_id=customer_id))
        except ValueError as error:
            flash(str(error), "error")
            customer = _customer_or_404(customer_id)

    return render_template("customer_form.html", customer=customer)


@app.post(f"{OFFICE_PREFIX}/customers/<int:customer_id>/delete")
@login_required
def customer_delete(customer_id: int):
    customer = _customer_or_404(customer_id)
    get_db().execute("DELETE FROM customers WHERE id = ?", (customer_id,))
    get_db().commit()
    flash(f"Заказчик «{customer['name']}» удалён вместе с историей поставок.", "success")
    return redirect(url_for("dashboard"))


@app.route(
    f"{OFFICE_PREFIX}/customers/<int:customer_id>/deployments/new",
    methods=["GET", "POST"],
)
@login_required
def deployment_new(customer_id: int):
    customer = _customer_or_404(customer_id)
    default_kind = request.args.get("kind", "update")
    if default_kind not in {"initial", "update"}:
        default_kind = "update"

    if request.method == "POST":
        try:
            kind = (request.form.get("kind") or "update").strip()
            if kind not in {"initial", "update"}:
                raise ValueError("Некорректный тип поставки.")
            version = (request.form.get("version") or "").strip()
            if not version:
                raise ValueError("Укажите версию PZ-Med.")
            installed_on = _validate_date(
                request.form.get("installed_on"), "Дата установки", required=True
            )
            get_db().execute(
                """
                INSERT INTO deployments(
                    customer_id, kind, version, installed_on, installation_id,
                    build_commit, sha256, notes, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    customer_id,
                    kind,
                    version,
                    installed_on,
                    (request.form.get("installation_id") or "").strip() or None,
                    (request.form.get("build_commit") or "").strip() or None,
                    (request.form.get("sha256") or "").strip() or None,
                    (request.form.get("notes") or "").strip() or None,
                    _now_iso(),
                ),
            )
            get_db().commit()
            flash("Запись о поставке сохранена.", "success")
            return redirect(url_for("customer_detail", customer_id=customer_id))
        except ValueError as error:
            flash(str(error), "error")
            default_kind = request.form.get("kind", default_kind)

    latest = get_db().execute(
        """
        SELECT installation_id FROM deployments
        WHERE customer_id = ? AND COALESCE(installation_id, '') <> ''
        ORDER BY installed_on DESC, id DESC LIMIT 1
        """,
        (customer_id,),
    ).fetchone()
    installation_id = latest["installation_id"] if latest else ""
    return render_template(
        "deployment_form.html",
        customer=customer,
        deployment=None,
        default_kind=default_kind,
        default_installation_id=installation_id,
        today=date.today().isoformat(),
    )


@app.route(f"{OFFICE_PREFIX}/deployments/<int:deployment_id>/edit", methods=["GET", "POST"])
@login_required
def deployment_edit(deployment_id: int):
    deployment = _deployment_or_404(deployment_id)
    customer = _customer_or_404(deployment["customer_id"])
    if request.method == "POST":
        try:
            kind = (request.form.get("kind") or "update").strip()
            if kind not in {"initial", "update"}:
                raise ValueError("Некорректный тип поставки.")
            version = (request.form.get("version") or "").strip()
            if not version:
                raise ValueError("Укажите версию PZ-Med.")
            installed_on = _validate_date(
                request.form.get("installed_on"), "Дата установки", required=True
            )
            get_db().execute(
                """
                UPDATE deployments SET
                    kind = ?, version = ?, installed_on = ?, installation_id = ?,
                    build_commit = ?, sha256 = ?, notes = ?
                WHERE id = ?
                """,
                (
                    kind,
                    version,
                    installed_on,
                    (request.form.get("installation_id") or "").strip() or None,
                    (request.form.get("build_commit") or "").strip() or None,
                    (request.form.get("sha256") or "").strip() or None,
                    (request.form.get("notes") or "").strip() or None,
                    deployment_id,
                ),
            )
            get_db().commit()
            flash("Запись о поставке обновлена.", "success")
            return redirect(url_for("customer_detail", customer_id=customer["id"]))
        except ValueError as error:
            flash(str(error), "error")
            deployment = _deployment_or_404(deployment_id)

    return render_template(
        "deployment_form.html",
        customer=customer,
        deployment=deployment,
        default_kind=deployment["kind"],
        default_installation_id=deployment["installation_id"] or "",
        today=date.today().isoformat(),
    )


@app.post(f"{OFFICE_PREFIX}/deployments/<int:deployment_id>/delete")
@login_required
def deployment_delete(deployment_id: int):
    deployment = _deployment_or_404(deployment_id)
    customer_id = deployment["customer_id"]
    get_db().execute("DELETE FROM deployments WHERE id = ?", (deployment_id,))
    get_db().commit()
    flash("Запись о поставке удалена.", "success")
    return redirect(url_for("customer_detail", customer_id=customer_id))


@app.route(f"{OFFICE_PREFIX}/account", methods=["GET", "POST"])
@login_required
def account():
    if request.method == "POST":
        current_password = request.form.get("current_password") or ""
        new_password = request.form.get("new_password") or ""
        confirmation = request.form.get("new_password_confirmation") or ""
        password_hash = _setting("admin_password_hash") or INITIAL_PASSWORD_HASH

        if not check_password_hash(password_hash, current_password):
            flash("Текущий пароль указан неверно.", "error")
        elif len(new_password) < 12:
            flash("Новый пароль должен содержать не менее 12 символов.", "error")
        elif new_password != confirmation:
            flash("Подтверждение нового пароля не совпадает.", "error")
        else:
            _set_setting("admin_password_hash", generate_password_hash(new_password))
            session.clear()
            flash("Пароль изменён. Войдите с новым паролем.", "success")
            return redirect(url_for("login"))

    return render_template("account.html")


@app.get(f"{OFFICE_PREFIX}/export.csv")
@login_required
def export_csv():
    rows = get_db().execute(
        """
        SELECT
            c.name, c.org_type, c.inn, c.contract_number, c.contract_date,
            c.support_until, c.it_contact,
            d.kind, d.version, d.installed_on, d.installation_id,
            d.build_commit, d.sha256, d.notes
        FROM customers c
        LEFT JOIN deployments d ON d.customer_id = c.id
        ORDER BY c.name COLLATE NOCASE, d.installed_on, d.id
        """
    ).fetchall()

    buffer = io.StringIO()
    writer = csv.writer(buffer, delimiter=";")
    writer.writerow(
        [
            "Заказчик",
            "Тип",
            "ИНН",
            "Договор",
            "Дата договора",
            "Поддержка до",
            "Контакт ИТ",
            "Тип поставки",
            "Версия",
            "Дата установки",
            "Installation ID",
            "Build commit",
            "SHA-256",
            "Примечание к поставке",
        ]
    )
    for row in rows:
        writer.writerow(
            [
                row["name"],
                "Государственная" if row["org_type"] == "state" else "Частная",
                row["inn"] or "",
                row["contract_number"] or "",
                row["contract_date"] or "",
                row["support_until"] or "",
                row["it_contact"] or "",
                "Первая установка" if row["kind"] == "initial" else ("Обновление" if row["kind"] else ""),
                row["version"] or "",
                row["installed_on"] or "",
                row["installation_id"] or "",
                row["build_commit"] or "",
                row["sha256"] or "",
                row["notes"] or "",
            ]
        )

    content = "\ufeff" + buffer.getvalue()
    filename = f"pz-med-deliveries-{date.today().isoformat()}.csv"
    return Response(
        content,
        content_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.errorhandler(400)
def bad_request(_error):
    return render_template("error.html", code=400, message="Некорректный запрос."), 400


@app.errorhandler(404)
def not_found(_error):
    return render_template("error.html", code=404, message="Страница не найдена."), 404


@app.errorhandler(413)
def too_large(_error):
    return render_template("error.html", code=413, message="Запрос слишком большой."), 413


init_db()
