from __future__ import annotations

from pathlib import Path
import re
import sqlite3

from flask import (
    Blueprint,
    abort,
    flash,
    redirect,
    render_template,
    request,
    send_file,
    url_for,
)

OFFICE_PREFIX = "/office"
_INSTALLATION_ID_RE = re.compile(r"^[A-Z0-9][A-Z0-9-]{5,79}$")
_LICENSE_ID_RE = re.compile(r"^CUL-[A-F0-9]{16}$")


def _connect(db_path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(db_path, timeout=10)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA journal_mode = WAL")
    connection.execute("PRAGMA busy_timeout = 10000")
    return connection


def _columns(connection: sqlite3.Connection, table: str) -> set[str]:
    return {row[1] for row in connection.execute(f"PRAGMA table_info({table})")}


def init_release_schema(db_path: Path) -> None:
    connection = _connect(db_path)
    try:
        customer_columns = _columns(connection, "customers")
        for name, definition in (
            ("release_code", "TEXT"),
            ("installation_id", "TEXT"),
            ("license_id", "TEXT"),
        ):
            if name not in customer_columns:
                connection.execute(f"ALTER TABLE customers ADD COLUMN {name} {definition}")

        deployment_columns = _columns(connection, "deployments")
        for name, definition in (
            ("license_id", "TEXT"),
            ("from_version", "TEXT"),
            ("archive_name", "TEXT"),
            ("archive_path", "TEXT"),
            ("release_message", "TEXT"),
            ("job_id", "INTEGER"),
            ("released_at", "TEXT"),
        ):
            if name not in deployment_columns:
                connection.execute(f"ALTER TABLE deployments ADD COLUMN {name} {definition}")

        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS release_jobs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                customer_id INTEGER NOT NULL,
                kind TEXT NOT NULL CHECK(kind IN ('initial', 'update')),
                bump_kind TEXT CHECK(bump_kind IN ('patch', 'minor', 'major') OR bump_kind IS NULL),
                status TEXT NOT NULL DEFAULT 'queued'
                    CHECK(status IN ('queued', 'building', 'ready', 'error')),
                requested_at TEXT NOT NULL,
                requested_commit TEXT,
                started_at TEXT,
                finished_at TEXT,
                version TEXT,
                build_commit TEXT,
                archive_name TEXT,
                archive_sha256 TEXT,
                deployment_id INTEGER,
                error_message TEXT,
                FOREIGN KEY(customer_id) REFERENCES customers(id) ON DELETE CASCADE
            );

            CREATE INDEX IF NOT EXISTS ix_release_jobs_customer_status
              ON release_jobs(customer_id, status, id DESC);

            CREATE TABLE IF NOT EXISTS release_status (
                id INTEGER PRIMARY KEY CHECK(id = 1),
                source_version TEXT,
                source_commit TEXT,
                official_version TEXT,
                official_commit TEXT,
                source_changed INTEGER NOT NULL DEFAULT 0,
                source_dirty INTEGER NOT NULL DEFAULT 0,
                checked_at TEXT,
                error_message TEXT
            );
            INSERT OR IGNORE INTO release_status(id) VALUES (1);
            """
        )
        job_columns = _columns(connection, "release_jobs")
        if "requested_commit" not in job_columns:
            connection.execute("ALTER TABLE release_jobs ADD COLUMN requested_commit TEXT")
        connection.commit()
    finally:
        connection.close()


def _next_version(version: str, kind: str) -> str:
    try:
        major, minor, patch = [int(part) for part in version.split(".")]
    except Exception:
        return "—"
    if kind == "patch":
        patch += 1
    elif kind == "minor":
        minor += 1
        patch = 0
    elif kind == "major":
        major += 1
        minor = 0
        patch = 0
    return f"{major}.{minor}.{patch}"


def _normalize_installation_id(value: str) -> str:
    normalized = str(value or "").strip().upper()
    if not _INSTALLATION_ID_RE.fullmatch(normalized):
        raise ValueError("Installation ID имеет некорректный формат")
    return normalized


def _normalize_license_id(value: str) -> str:
    normalized = str(value or "").strip().upper()
    if not _LICENSE_ID_RE.fullmatch(normalized):
        raise ValueError("License ID должен иметь формат CUL-XXXXXXXXXXXXXXXX")
    return normalized


def register_release_features(
    app,
    *,
    db_path: Path,
    releases_dir: Path,
    get_db,
    login_required,
    customer_or_404,
    now_iso,
) -> None:
    init_release_schema(db_path)
    releases_dir.mkdir(parents=True, exist_ok=True)
    bp = Blueprint("release", __name__)

    def status_row():
        return get_db().execute("SELECT * FROM release_status WHERE id = 1").fetchone()

    def pending_job(customer_id: int):
        return get_db().execute(
            """
            SELECT * FROM release_jobs
            WHERE customer_id = ?
            ORDER BY id DESC LIMIT 1
            """,
            (customer_id,),
        ).fetchone()

    def latest_message(customer_id: int):
        return get_db().execute(
            """
            SELECT id, version, kind, release_message, archive_name, archive_path
            FROM deployments
            WHERE customer_id = ? AND COALESCE(release_message, '') <> ''
            ORDER BY installed_on DESC, id DESC LIMIT 1
            """,
            (customer_id,),
        ).fetchone()

    def latest_deployment(customer_id: int):
        return get_db().execute(
            """
            SELECT * FROM deployments
            WHERE customer_id = ?
            ORDER BY installed_on DESC, id DESC LIMIT 1
            """,
            (customer_id,),
        ).fetchone()

    @app.context_processor
    def _release_context():
        return {
            "office_release_status": status_row,
            "office_pending_job": pending_job,
            "office_latest_release_message": latest_message,
            "office_latest_deployment": latest_deployment,
            "office_next_version": _next_version,
        }

    @bp.route(f"{OFFICE_PREFIX}/customers/<int:customer_id>/release/<kind>", methods=["GET", "POST"])
    @login_required
    def request_release(customer_id: int, kind: str):
        if kind not in {"initial", "update"}:
            abort(404)
        customer = customer_or_404(customer_id)
        latest = latest_deployment(customer_id)
        if kind == "initial" and latest is not None:
            flash("Первичная поставка уже создана. Для этой организации формируй обновление.", "error")
            return redirect(url_for("customer_detail", customer_id=customer_id))
        if kind == "update" and latest is None:
            flash("Сначала нужно сформировать первичную поставку.", "error")
            return redirect(url_for("customer_detail", customer_id=customer_id))

        active = get_db().execute(
            """
            SELECT id FROM release_jobs
            WHERE customer_id = ? AND status IN ('queued', 'building')
            LIMIT 1
            """,
            (customer_id,),
        ).fetchone()
        if active:
            flash("Для этого заказчика уже выполняется сборка.", "error")
            return redirect(url_for("customer_detail", customer_id=customer_id))

        status = status_row()
        source_changed = bool(status and status["source_changed"])
        source_dirty = bool(status and status["source_dirty"])
        official_version = (status["official_version"] if status else None) or (
            status["source_version"] if status else None
        )
        existing_installation_id = str(
            (customer["installation_id"] if customer else None)
            or (latest["installation_id"] if latest else None)
            or ""
        ).strip()
        existing_license_id = str(
            (customer["license_id"] if customer else None)
            or (latest["license_id"] if latest else None)
            or ""
        ).strip()

        if request.method == "POST":
            if source_dirty:
                flash("Release-репозиторий содержит незакоммиченные изменения. Сборка заблокирована.", "error")
                return redirect(request.url)

            if kind == "update":
                try:
                    installation_id = _normalize_installation_id(
                        request.form.get("installation_id") or existing_installation_id
                    )
                    license_id = _normalize_license_id(
                        request.form.get("license_id") or existing_license_id
                    )
                except ValueError as error:
                    flash(str(error), "error")
                    return redirect(request.url)

                conflict = get_db().execute(
                    """
                    SELECT id, installation_id, license_id FROM deployments
                    WHERE customer_id = ? AND (
                        (COALESCE(installation_id, '') <> '' AND installation_id <> ?)
                        OR (COALESCE(license_id, '') <> '' AND license_id <> ?)
                    ) LIMIT 1
                    """,
                    (customer_id, installation_id, license_id),
                ).fetchone()
                if conflict:
                    flash(
                        "В истории этой организации уже есть другая пара Installation ID / License ID. "
                        "Сборка заблокирована до исправления истории.",
                        "error",
                    )
                    return redirect(request.url)

                get_db().execute(
                    """
                    UPDATE customers SET installation_id = ?, license_id = ?, updated_at = ?
                    WHERE id = ?
                    """,
                    (installation_id, license_id, now_iso(), customer_id),
                )
                get_db().execute(
                    """
                    UPDATE deployments SET
                        installation_id = CASE
                            WHEN COALESCE(installation_id, '') = '' THEN ? ELSE installation_id END,
                        license_id = CASE
                            WHEN COALESCE(license_id, '') = '' THEN ? ELSE license_id END
                    WHERE customer_id = ?
                    """,
                    (installation_id, license_id, customer_id),
                )

            bump_kind = (request.form.get("bump_kind") or "").strip() or None
            if source_changed and status and status["official_commit"]:
                if bump_kind not in {"patch", "minor", "major"}:
                    flash("Выбери значимость новой версии.", "error")
                    get_db().rollback()
                    return redirect(request.url)
            else:
                bump_kind = None

            get_db().execute(
                """
                INSERT INTO release_jobs(
                    customer_id, kind, bump_kind, status, requested_at, requested_commit
                ) VALUES (?, ?, ?, 'queued', ?, ?)
                """,
                (customer_id, kind, bump_kind, now_iso(), status["source_commit"] if status else None),
            )
            get_db().commit()
            flash("Сборка поставлена в очередь. Карточка заполнится автоматически после завершения.", "success")
            return redirect(url_for("customer_detail", customer_id=customer_id))

        return render_template(
            "release_request.html",
            customer=customer,
            kind=kind,
            latest=latest,
            status=status,
            source_changed=source_changed,
            source_dirty=source_dirty,
            official_version=official_version,
            existing_installation_id=existing_installation_id,
            existing_license_id=existing_license_id,
        )

    @bp.get(f"{OFFICE_PREFIX}/release-jobs/<int:job_id>/status")
    @login_required
    def job_status(job_id: int):
        row = get_db().execute(
            "SELECT id, customer_id, status, error_message FROM release_jobs WHERE id = ?",
            (job_id,),
        ).fetchone()
        if row is None:
            abort(404)
        return {
            "id": row["id"],
            "status": row["status"],
            "error": row["error_message"],
            "redirect": url_for("customer_detail", customer_id=row["customer_id"]),
        }

    @bp.get(f"{OFFICE_PREFIX}/deployments/<int:deployment_id>/download")
    @login_required
    def download_release(deployment_id: int):
        row = get_db().execute(
            "SELECT archive_name, archive_path FROM deployments WHERE id = ?",
            (deployment_id,),
        ).fetchone()
        if row is None or not row["archive_path"]:
            abort(404)
        path = Path(row["archive_path"]).expanduser().resolve()
        allowed = releases_dir.expanduser().resolve()
        try:
            path.relative_to(allowed)
        except ValueError:
            abort(403)
        if not path.is_file():
            abort(404)
        return send_file(
            path,
            as_attachment=True,
            download_name=row["archive_name"] or path.name,
            conditional=True,
            max_age=0,
        )

    app.register_blueprint(bp)
