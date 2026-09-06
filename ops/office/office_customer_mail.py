from __future__ import annotations

import re
import sqlite3
from datetime import datetime
from pathlib import Path

from flask import abort, flash, g, redirect, request, url_for

from office_mail import MailError, _list_messages


OFFICE_PREFIX = "/office"
_EMAIL_RE = re.compile(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", re.IGNORECASE)


def _emails_from(value: str | None) -> set[str]:
    if not value:
        return set()
    return {item.casefold() for item in _EMAIL_RE.findall(value)}


def _valid_email(value: str) -> bool:
    return bool(value and _EMAIL_RE.fullmatch(value.strip()))


def register_customer_mail_features(app, *, db_path: Path, get_db, login_required) -> None:
    connection = sqlite3.connect(db_path)
    try:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS customer_emails (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                customer_id INTEGER NOT NULL,
                email TEXT NOT NULL COLLATE NOCASE,
                label TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (customer_id) REFERENCES customers(id) ON DELETE CASCADE,
                UNIQUE(email)
            );
            CREATE INDEX IF NOT EXISTS ix_customer_emails_customer
                ON customer_emails(customer_id, id);
            """
        )
        connection.commit()
    finally:
        connection.close()

    def linked_emails(customer_id: int) -> list[dict[str, object]]:
        rows = get_db().execute(
            "SELECT id, email, label FROM customer_emails WHERE customer_id = ? ORDER BY id",
            (customer_id,),
        ).fetchall()
        return [dict(row) for row in rows]

    def all_customer_emails(customer) -> list[str]:
        result: list[str] = []
        for row in linked_emails(customer["id"]):
            email = str(row["email"]).strip()
            if email and email.casefold() not in {item.casefold() for item in result}:
                result.append(email)
        for email in _EMAIL_RE.findall(customer["it_contact"] or ""):
            if email.casefold() not in {item.casefold() for item in result}:
                result.append(email)
        return result

    def customer_email_map() -> dict[str, dict[str, object]]:
        cached = getattr(g, "office_customer_email_map", None)
        if cached is not None:
            return cached

        result: dict[str, dict[str, object]] = {}
        rows = get_db().execute(
            "SELECT id, name, it_contact FROM customers ORDER BY name COLLATE NOCASE"
        ).fetchall()
        for row in rows:
            customer = {"id": row["id"], "name": row["name"]}
            for email in _emails_from(row["it_contact"]):
                result.setdefault(email, customer)

        linked = get_db().execute(
            """
            SELECT ce.email, c.id, c.name
            FROM customer_emails ce
            JOIN customers c ON c.id = ce.customer_id
            ORDER BY c.name COLLATE NOCASE
            """
        ).fetchall()
        for row in linked:
            result[row["email"].casefold()] = {"id": row["id"], "name": row["name"]}

        g.office_customer_email_map = result
        return result

    def primary_email(customer) -> str:
        emails = all_customer_emails(customer)
        return emails[0] if emails else ""

    def match_customer(*values: str | None):
        mapping = customer_email_map()
        for value in values:
            for email in _emails_from(value):
                customer = mapping.get(email)
                if customer:
                    return customer
        return None

    def mail_history(customer, limit: int = 12) -> list[dict[str, object]]:
        emails = all_customer_emails(customer)
        if not emails:
            return []
        wanted = {item.casefold() for item in emails}
        items: list[dict[str, object]] = []
        try:
            for folder, direction in (("inbox", "Входящее"), ("sent", "Исходящее")):
                # Получаем последние письма папки и отбираем только те, где есть
                # любой e-mail, привязанный к карточке заказчика.
                messages, _unread, _folders = _list_messages(folder, "")
                for item in messages:
                    address_values = " ".join(
                        str(item.get(key) or "")
                        for key in ("from_address", "to_display")
                    )
                    if not (_emails_from(address_values) & wanted):
                        continue
                    copy = dict(item)
                    copy["folder"] = folder
                    copy["direction"] = direction
                    copy["url"] = url_for("mail_message", uid=item["uid"], folder=folder)
                    try:
                        copy["sort_date"] = datetime.strptime(str(item.get("date") or ""), "%d.%m.%Y %H:%M")
                    except ValueError:
                        copy["sort_date"] = datetime.min
                    items.append(copy)
        except MailError:
            return []

        items.sort(key=lambda item: item["sort_date"], reverse=True)
        return items[: max(1, min(limit, 30))]

    @app.post(f"{OFFICE_PREFIX}/customers/<int:customer_id>/emails")
    @login_required
    def customer_email_add(customer_id: int):
        customer = get_db().execute("SELECT id, name FROM customers WHERE id = ?", (customer_id,)).fetchone()
        if customer is None:
            abort(404)
        email = (request.form.get("email") or "").strip().lower()
        label = (request.form.get("label") or "").strip()[:120] or None
        if not _valid_email(email):
            flash("Укажите корректный e-mail.", "error")
            return redirect(url_for("customer_detail", customer_id=customer_id))
        try:
            get_db().execute(
                "INSERT INTO customer_emails(customer_id, email, label) VALUES (?, ?, ?)",
                (customer_id, email, label),
            )
            get_db().commit()
            g.pop("office_customer_email_map", None)
            flash("E-mail привязан к карточке заказчика.", "success")
        except sqlite3.IntegrityError:
            row = get_db().execute(
                "SELECT c.id, c.name FROM customer_emails ce JOIN customers c ON c.id = ce.customer_id WHERE ce.email = ?",
                (email,),
            ).fetchone()
            if row and row["id"] != customer_id:
                flash(f"Этот e-mail уже привязан к заказчику «{row['name']}».", "error")
            else:
                flash("Этот e-mail уже привязан к карточке.", "error")
        return redirect(url_for("customer_detail", customer_id=customer_id))

    @app.post(f"{OFFICE_PREFIX}/customers/<int:customer_id>/emails/<int:email_id>/delete")
    @login_required
    def customer_email_delete(customer_id: int, email_id: int):
        cursor = get_db().execute(
            "DELETE FROM customer_emails WHERE id = ? AND customer_id = ?",
            (email_id, customer_id),
        )
        get_db().commit()
        g.pop("office_customer_email_map", None)
        if cursor.rowcount:
            flash("E-mail отвязан от карточки.", "success")
        return redirect(url_for("customer_detail", customer_id=customer_id))

    @app.context_processor
    def _customer_mail_context():
        return {
            "office_mail_customer": match_customer,
            "office_customer_primary_email": primary_email,
            "office_customer_emails": linked_emails,
            "office_customer_all_emails": all_customer_emails,
            "office_customer_mail_history": mail_history,
        }
