#!/usr/bin/env python3
"""Root-only worker for PZ-Med Office release jobs.

The web application can only enqueue a strongly typed job in SQLite. This worker
validates the repository state and invokes fixed release scripts; no shell text
from the browser is ever executed.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from pathlib import Path
import json
import os
import pwd
import shutil
import sqlite3
import subprocess
import time

from office_release import init_release_schema

DB_PATH = Path(os.environ.get("OFFICE_DB_PATH", "/var/lib/pz-med-office/office.sqlite3"))
RELEASES_DIR = Path(os.environ.get("OFFICE_RELEASES_DIR", "/var/lib/pz-med-office/releases"))
SOURCE = Path(os.environ.get("CLINIC_RELEASE_SOURCE", "/root/medical_cards/clinic_universal_stage2_test"))
SOURCE_PYTHON = Path(os.environ.get("CLINIC_RELEASE_PYTHON", SOURCE / "venv/bin/python"))
REGISTRY_ROOT = Path(os.environ.get("CLINIC_CUSTOMER_REGISTRY", "/root/.clinic-universal-release/customers"))
DELIVERY_ROOT = Path(os.environ.get("CLINIC_DELIVERY_ROOT", "/root/clinic-universal-deliveries"))
SIGNING_KEY = Path(os.environ.get("CLINIC_RELEASE_SIGNING_KEY", "/root/.clinic-universal-release/signing-private.pem"))
STATE_DIR = Path(os.environ.get("PZ_MED_RELEASE_STATE_DIR", "/var/lib/pz-med-release"))
STATE_FILE = STATE_DIR / "state.json"
OFFICE_USER = os.environ.get("OFFICE_USER", "pz-med-office")
POLL_SECONDS = max(1.0, float(os.environ.get("PZ_MED_RELEASE_POLL_SECONDS", "2")))
BUILD_TIMEOUT = max(300, int(os.environ.get("PZ_MED_RELEASE_BUILD_TIMEOUT", "7200")))


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def db() -> sqlite3.Connection:
    connection = sqlite3.connect(DB_PATH, timeout=30)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA journal_mode = WAL")
    connection.execute("PRAGMA busy_timeout = 30000")
    return connection


def run(*args: str, timeout: int = 30) -> str:
    result = subprocess.run(
        list(args),
        cwd=SOURCE,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        timeout=timeout,
    )
    if result.returncode != 0:
        raise RuntimeError((result.stderr or result.stdout).strip() or f"Команда завершилась с кодом {result.returncode}")
    return result.stdout.strip()


def source_info() -> dict:
    if not (SOURCE / ".git").exists():
        raise RuntimeError(f"Release source не является Git-репозиторием: {SOURCE}")
    if not (SOURCE / "VERSION").is_file():
        raise RuntimeError(f"Не найден {SOURCE / 'VERSION'}")
    if not SOURCE_PYTHON.is_file():
        raise RuntimeError(f"Не найден release Python: {SOURCE_PYTHON}")
    if not SIGNING_KEY.is_file():
        raise RuntimeError(f"Не найден signing key: {SIGNING_KEY}")

    commit = run("git", "rev-parse", "HEAD")
    version = (SOURCE / "VERSION").read_text(encoding="utf-8").strip()
    status = run("git", "status", "--porcelain")
    dirty_lines = []
    for line in status.splitlines():
        path = line[3:].strip() if len(line) >= 4 else line.strip()
        normalized = path.replace("\\", "/")
        if normalized in {
            "app/static/css/core.min.css",
            "app/static/css/ui.min.css",
        }:
            continue
        dirty_lines.append(line)
    return {
        "commit": commit,
        "version": version,
        "dirty": bool(dirty_lines),
        "dirty_details": "\n".join(dirty_lines[:20]),
    }


def read_state() -> dict:
    if not STATE_FILE.is_file():
        return {}
    try:
        payload = json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except Exception as error:
        raise RuntimeError(f"Не удалось прочитать release state: {error}") from error
    return payload if isinstance(payload, dict) else {}


def write_state(version: str, commit: str) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    STATE_DIR.chmod(0o700)
    payload = {
        "schema_version": 1,
        "official_version": version,
        "official_commit": commit,
        "released_at": now_iso(),
    }
    temporary = STATE_FILE.with_suffix(".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.chmod(0o600)
    os.replace(temporary, STATE_FILE)
    STATE_FILE.chmod(0o600)


def bump(version: str, kind: str) -> str:
    try:
        major, minor, patch = [int(part) for part in version.split(".")]
    except Exception as error:
        raise RuntimeError(f"Некорректная официальная версия {version!r}") from error
    if kind == "patch":
        patch += 1
    elif kind == "minor":
        minor += 1
        patch = 0
    elif kind == "major":
        major += 1
        minor = 0
        patch = 0
    else:
        raise RuntimeError("Для нового релиза требуется patch, minor или major")
    return f"{major}.{minor}.{patch}"


def update_mirror_status(error: str | None = None) -> dict | None:
    try:
        info = source_info()
        state = read_state()
        official_version = state.get("official_version")
        official_commit = state.get("official_commit")
        source_changed = bool(official_commit and info["commit"] != official_commit)
        with db() as connection:
            connection.execute(
                """
                UPDATE release_status SET
                    source_version = ?, source_commit = ?,
                    official_version = ?, official_commit = ?,
                    source_changed = ?, source_dirty = ?, checked_at = ?, error_message = ?
                WHERE id = 1
                """,
                (
                    info["version"], info["commit"], official_version, official_commit,
                    int(source_changed), int(info["dirty"]), now_iso(), error,
                ),
            )
        return {**info, **state, "source_changed": source_changed}
    except Exception as exc:
        try:
            with db() as connection:
                connection.execute(
                    "UPDATE release_status SET checked_at = ?, error_message = ? WHERE id = 1",
                    (now_iso(), str(exc)[:2000]),
                )
        except Exception:
            pass
        return None


def claim_job() -> sqlite3.Row | None:
    connection = db()
    try:
        connection.execute("BEGIN IMMEDIATE")
        row = connection.execute(
            "SELECT * FROM release_jobs WHERE status = 'queued' ORDER BY id LIMIT 1"
        ).fetchone()
        if row is None:
            connection.commit()
            return None
        connection.execute(
            "UPDATE release_jobs SET status = 'building', started_at = ?, error_message = NULL WHERE id = ?",
            (now_iso(), row["id"]),
        )
        connection.commit()
        return row
    finally:
        connection.close()


def release_code(customer_id: int) -> str:
    return f"pz{customer_id:06d}"


def load_registry_customer(code: str) -> dict:
    path = REGISTRY_ROOT / code / "customer.json"
    return json.loads(path.read_text(encoding="utf-8"))


def load_registry_history(code: str) -> list[dict]:
    path = REGISTRY_ROOT / code / "release_history.jsonl"
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def ensure_web_release_copy(customer_id: int, archive_path: Path) -> Path:
    account = pwd.getpwnam(OFFICE_USER)
    target_dir = RELEASES_DIR / str(customer_id)
    target_dir.mkdir(parents=True, exist_ok=True)
    os.chown(target_dir, account.pw_uid, account.pw_gid)
    target_dir.chmod(0o750)
    target = target_dir / archive_path.name
    shutil.copy2(archive_path, target)
    os.chown(target, account.pw_uid, account.pw_gid)
    target.chmod(0o640)
    return target


def initial_message(customer: sqlite3.Row, release: dict, registry_customer: dict) -> str:
    archive = release["archive_name"]
    return f"""Добрый день.

Направляю персональную поставку PZ-Med версии {release['version']} для организации «{customer['name']}».

Installation ID: {registry_customer['installation_id']}
License ID: {registry_customer['license_id']}
Build commit: {release['build_commit']}
Архив: {archive}
SHA-256: {release['archive_sha256']}

Перед установкой проверьте архив:
  sha256sum {archive}

Краткая установка:
  tar -xzf {archive}
  cd clinic_universal
  sha256sum -c SHA256SUMS
  sudo bash ./deploy/bootstrap-root.sh
  sudo -u clinic-universal -H /opt/clinic-universal/deploy/install.sh
  sudo systemctl enable --now clinic_universal

После установки проверьте:
  systemctl status clinic_universal --no-pager
  curl -I http://127.0.0.1:5001/

Полная инструкция находится внутри архива: deploy/README_INSTALL.txt.
Если при проверке SHA-256 или production preflight возникает ошибка, установку продолжать не следует — пришлите мне вывод команды.
""".strip()


def update_message(customer: sqlite3.Row, release: dict, registry_customer: dict) -> str:
    archive = release["archive_name"]
    return f"""Добрый день.

Направляю персональное обновление PZ-Med для организации «{customer['name']}»:
{release.get('from_version') or 'предыдущая версия'} → {release['version']}.

Installation ID: {registry_customer['installation_id']}
License ID: {registry_customer['license_id']}
Build commit: {release['build_commit']}
Архив: {archive}
SHA-256: {release['archive_sha256']}

Перед обновлением проверьте архив:
  sha256sum {archive}

Краткая установка обновления:
  tar -xzf {archive}
  cd pz_med_update
  sudo bash ./apply-update.sh

Установщик сам проверит Installation ID и исходную версию, остановит сервис, создаст резервную копию БД, сохранит пользовательские данные, применит код/зависимости/миграции и запустит сервис обратно.

Полная инструкция находится внутри архива: README_UPDATE.txt.
Если обновление завершится ошибкой, сервис намеренно останется остановленным, а путь к резервной копии будет показан в терминале — пришлите мне весь вывод.
""".strip()


def cleanup_failed_release(code: str, kind: str, version: str) -> None:
    try:
        history = load_registry_history(code) if (REGISTRY_ROOT / code / "release_history.jsonl").is_file() else []
        if any(row.get("version") == version for row in history):
            return
        path = DELIVERY_ROOT / code
        path = path / (f"v{version}" if kind == "initial" else f"updates/v{version}")
        resolved = path.resolve()
        resolved.relative_to(DELIVERY_ROOT.resolve())
        if resolved.is_dir():
            shutil.rmtree(resolved)
    except Exception:
        pass


def fail_job(job_id: int, error: Exception | str) -> None:
    message = str(error).strip() or "Неизвестная ошибка сборки"
    with db() as connection:
        connection.execute(
            "UPDATE release_jobs SET status = 'error', finished_at = ?, error_message = ? WHERE id = ?",
            (now_iso(), message[-5000:], job_id),
        )
    print(f"release job {job_id}: ERROR: {message}", flush=True)


def process_job(job: sqlite3.Row) -> None:
    info = source_info()
    if info["dirty"]:
        raise RuntimeError(
            "Release source содержит незакоммиченные изменения:\n" + (info["dirty_details"] or "dirty")
        )
    if job["requested_commit"] and job["requested_commit"] != info["commit"]:
        raise RuntimeError(
            "Код PZ-Med изменился после постановки сборки в очередь. Открой карточку и запусти сборку заново."
        )

    state = read_state()
    official_version = state.get("official_version")
    official_commit = state.get("official_commit")
    new_global_release = False
    if not official_commit:
        target_version = info["version"]
        new_global_release = True
    elif info["commit"] == official_commit:
        target_version = str(official_version)
    else:
        if job["bump_kind"] not in {"patch", "minor", "major"}:
            raise RuntimeError("Исходный код изменился: для нового релиза нужно выбрать patch/minor/major")
        target_version = bump(str(official_version), job["bump_kind"])
        new_global_release = True

    connection = db()
    try:
        customer = connection.execute("SELECT * FROM customers WHERE id = ?", (job["customer_id"],)).fetchone()
        if customer is None:
            raise RuntimeError("Заказчик удалён")
        latest = connection.execute(
            "SELECT * FROM deployments WHERE customer_id = ? ORDER BY installed_on DESC, id DESC LIMIT 1",
            (customer["id"],),
        ).fetchone()
    finally:
        connection.close()

    kind = job["kind"]
    if kind == "initial" and latest is not None:
        raise RuntimeError("Первичная поставка уже существует")
    if kind == "update" and latest is None:
        raise RuntimeError("Невозможно создать обновление до первичной поставки")
    if kind == "update" and latest["version"] == target_version:
        raise RuntimeError(f"У заказчика уже сформирована актуальная версия {target_version}")

    code = customer["release_code"] or release_code(customer["id"])
    common = [
        str(SOURCE_PYTHON),
        str(SOURCE / "scripts" / ("office_customer_release.py" if kind == "initial" else "customer_update_release.py")),
        "--registry-root", str(REGISTRY_ROOT),
        "--delivery-root", str(DELIVERY_ROOT),
        "--code", code,
        "--version", target_version,
        "--signing-key", str(SIGNING_KEY),
    ]
    if kind == "initial":
        common.extend(["--licensee", customer["name"]])

    result = subprocess.run(
        common,
        cwd=SOURCE,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
        timeout=BUILD_TIMEOUT,
    )
    if result.returncode != 0:
        cleanup_failed_release(code, kind, target_version)
        raise RuntimeError(result.stdout[-5000:] or f"Release builder завершился с кодом {result.returncode}")

    registry_customer = load_registry_customer(code)
    history = load_registry_history(code)
    if not history:
        raise RuntimeError("Release builder завершился без записи history")
    release = history[-1]
    if release.get("version") != target_version:
        raise RuntimeError("Версия в release history не совпадает с ожидаемой")

    if kind == "initial":
        archive_path = DELIVERY_ROOT / code / f"v{target_version}" / release["archive_name"]
        message = initial_message(customer, release, registry_customer)
        from_version = None
    else:
        archive_path = DELIVERY_ROOT / code / "updates" / f"v{target_version}" / release["archive_name"]
        message = update_message(customer, release, registry_customer)
        from_version = release.get("from_version")
    if not archive_path.is_file():
        raise RuntimeError(f"Готовый архив не найден: {archive_path}")
    web_archive = ensure_web_release_copy(customer["id"], archive_path)

    installed_on = date.today().isoformat()
    with db() as connection:
        cursor = connection.execute(
            """
            INSERT INTO deployments(
                customer_id, kind, version, installed_on, installation_id,
                build_commit, sha256, notes, created_at, license_id, from_version,
                archive_name, archive_path, release_message, job_id, released_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                customer["id"], kind, target_version, installed_on,
                registry_customer["installation_id"], release.get("build_commit"),
                release.get("archive_sha256"), "Сформировано автоматически через PZ-Med Office",
                now_iso(), registry_customer["license_id"], from_version,
                release["archive_name"], str(web_archive), message, job["id"],
                release.get("released_at") or now_iso(),
            ),
        )
        deployment_id = cursor.lastrowid
        connection.execute(
            """
            UPDATE customers SET release_code = ?, installation_id = ?, license_id = ?, updated_at = ?
            WHERE id = ?
            """,
            (code, registry_customer["installation_id"], registry_customer["license_id"], now_iso(), customer["id"]),
        )
        connection.execute(
            """
            UPDATE release_jobs SET status = 'ready', finished_at = ?, version = ?,
                build_commit = ?, archive_name = ?, archive_sha256 = ?, deployment_id = ?, error_message = NULL
            WHERE id = ?
            """,
            (
                now_iso(), target_version, release.get("build_commit"), release["archive_name"],
                release.get("archive_sha256"), deployment_id, job["id"],
            ),
        )

    if new_global_release:
        write_state(target_version, info["commit"])
    print(f"release job {job['id']}: READY {kind} {customer['name']} -> {target_version}", flush=True)


def main() -> int:
    if os.geteuid() != 0:
        raise SystemExit("release_worker.py должен работать только как root systemd service")
    init_release_schema(DB_PATH)
    RELEASES_DIR.mkdir(parents=True, exist_ok=True)
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    STATE_DIR.chmod(0o700)
    print("PZ-Med release worker started", flush=True)
    while True:
        update_mirror_status()
        job = claim_job()
        if job is None:
            time.sleep(POLL_SECONDS)
            continue
        try:
            process_job(job)
        except subprocess.TimeoutExpired:
            fail_job(job["id"], f"Сборка превысила лимит {BUILD_TIMEOUT} секунд")
        except Exception as error:
            fail_job(job["id"], error)
        update_mirror_status()


if __name__ == "__main__":
    raise SystemExit(main())
