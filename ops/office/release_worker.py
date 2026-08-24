#!/usr/bin/env python3
"""PZ-Med release worker entrypoint with existing-installation synchronization.

Основной worker сохранён в release_worker_core.py. Перед update-задачей этот
entrypoint синхронизирует вручную внесённую историю Office с закрытым customer
registry, переиспользуя уже выданные Installation ID / License ID.
"""

from __future__ import annotations

from pathlib import Path
import json
import subprocess

import release_worker_core as core


_core_process_job = core.process_job


def _read_registry_customer(path: Path) -> dict | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return payload if isinstance(payload, dict) else None


def _find_existing_registry_code(installation_id: str, license_id: str) -> str | None:
    if not core.REGISTRY_ROOT.is_dir():
        return None
    exact: list[str] = []
    conflicts: list[str] = []
    for path in sorted(core.REGISTRY_ROOT.glob("*/customer.json")):
        payload = _read_registry_customer(path)
        if not payload:
            continue
        stored_installation = str(payload.get("installation_id") or "").strip()
        stored_license = str(payload.get("license_id") or "").strip()
        installation_match = stored_installation == installation_id
        license_match = stored_license == license_id
        if installation_match and license_match:
            exact.append(str(payload.get("code") or path.parent.name))
        elif installation_match or license_match:
            conflicts.append(str(payload.get("code") or path.parent.name))
    if conflicts:
        raise RuntimeError(
            "Закрытый release registry содержит конфликт Installation ID / License ID: "
            + ", ".join(conflicts)
        )
    if len(exact) > 1:
        raise RuntimeError(
            "Одна и та же пара Installation ID / License ID встречается в нескольких customer registry: "
            + ", ".join(exact)
        )
    return exact[0] if exact else None


def _sync_existing_installation(customer_id: int) -> None:
    connection = core.db()
    try:
        customer = connection.execute(
            "SELECT * FROM customers WHERE id = ?", (customer_id,)
        ).fetchone()
        if customer is None:
            raise RuntimeError("Заказчик удалён")
        deployments = connection.execute(
            """
            SELECT * FROM deployments
            WHERE customer_id = ?
            ORDER BY installed_on ASC, id ASC
            """,
            (customer_id,),
        ).fetchall()
    finally:
        connection.close()

    if not deployments:
        raise RuntimeError("Для существующей установки нет истории поставок в Office")

    latest = deployments[-1]
    installation_id = str(
        customer["installation_id"] or latest["installation_id"] or ""
    ).strip()
    license_id = str(
        customer["license_id"] or latest["license_id"] or ""
    ).strip()
    if not installation_id:
        raise RuntimeError(
            "Для существующей установки не указан Installation ID. "
            "Открой форму формирования обновления и укажи выданный Installation ID."
        )
    if not license_id:
        raise RuntimeError(
            "Для существующей установки не указан License ID. "
            "Открой форму формирования обновления и укажи выданный License ID."
        )

    existing_code = _find_existing_registry_code(installation_id, license_id)
    configured_code = str(customer["release_code"] or "").strip()
    if existing_code and configured_code and existing_code != configured_code:
        raise RuntimeError(
            f"Карточка Office привязана к release code {configured_code}, "
            f"но Installation ID / License ID уже зарегистрированы как {existing_code}."
        )
    code = existing_code or configured_code or core.release_code(customer_id)

    history = []
    for deployment in deployments:
        history.append(
            {
                "kind": deployment["kind"],
                "version": deployment["version"],
                "installed_on": deployment["installed_on"],
                "build_commit": deployment["build_commit"],
                "sha256": deployment["sha256"],
                "archive_name": deployment["archive_name"],
            }
        )

    importer = core.SOURCE / "scripts" / "import_existing_customer_history.py"
    if not importer.is_file():
        raise RuntimeError(
            "Release source ещё не содержит import_existing_customer_history.py. "
            "Сначала выполни clinic-test-update."
        )
    command = [
        str(core.SOURCE_PYTHON),
        str(importer),
        "--registry-root", str(core.REGISTRY_ROOT),
        "--code", code,
        "--licensee", customer["name"],
        "--installation-id", installation_id,
        "--license-id", license_id,
        "--history-json", json.dumps(history, ensure_ascii=False),
    ]
    result = subprocess.run(
        command,
        cwd=core.SOURCE,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
        timeout=120,
    )
    if result.returncode != 0:
        raise RuntimeError(
            "Не удалось синхронизировать существующую установку с release registry:\n"
            + (result.stdout[-5000:] or f"код {result.returncode}")
        )

    with core.db() as connection:
        connection.execute(
            """
            UPDATE customers SET
                release_code = ?, installation_id = ?, license_id = ?, updated_at = ?
            WHERE id = ?
            """,
            (code, installation_id, license_id, core.now_iso(), customer_id),
        )


def process_job(job):
    if job["kind"] == "update":
        _sync_existing_installation(job["customer_id"])
    return _core_process_job(job)


# core.main() обращается к global process_job своего модуля; подменяем только
# точку обработки задачи, оставляя claim/status/versioning и security прежними.
core.process_job = process_job


def main() -> int:
    return core.main()


if __name__ == "__main__":
    raise SystemExit(main())
