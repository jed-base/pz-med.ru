from __future__ import annotations

import re
from datetime import datetime

from flask import g, url_for

from office_mail import MailError, _list_messages


_EMAIL_RE = re.compile(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", re.IGNORECASE)


def _emails_from(value: str | None) -> set[str]:
    if not value:
        return set()
    return {item.casefold() for item in _EMAIL_RE.findall(value)}


def register_customer_mail_features(app, *, get_db) -> None:
    def customer_email_map() -> dict[str, dict[str, object]]:
        cached = getattr(g, "office_customer_email_map", None)
        if cached is not None:
            return cached

        result: dict[str, dict[str, object]] = {}
        rows = get_db().execute(
            "SELECT id, name, contact_email, it_contact FROM customers ORDER BY name COLLATE NOCASE"
        ).fetchall()
        for row in rows:
            emails = set()
            emails.update(_emails_from(row["contact_email"]))
            emails.update(_emails_from(row["it_contact"]))
            customer = {"id": row["id"], "name": row["name"]}
            for email in emails:
                result.setdefault(email, customer)
        g.office_customer_email_map = result
        return result

    def primary_email(customer) -> str:
        explicit = (customer["contact_email"] or "").strip() if "contact_email" in customer.keys() else ""
        if explicit:
            return explicit
        found = _EMAIL_RE.findall(customer["it_contact"] or "")
        return found[0] if found else ""

    def match_customer(*values: str | None):
        mapping = customer_email_map()
        for value in values:
            for email in _emails_from(value):
                customer = mapping.get(email)
                if customer:
                    return customer
        return None

    def mail_history(customer, limit: int = 12) -> list[dict[str, object]]:
        email = primary_email(customer)
        if not email:
            return []
        items: list[dict[str, object]] = []
        try:
            for folder, direction in (("inbox", "Входящее"), ("sent", "Исходящее")):
                messages, _unread, _folders = _list_messages(folder, email)
                for item in messages:
                    addresses = " ".join(
                        str(item.get(key) or "")
                        for key in ("from_address", "to_display")
                    ).casefold()
                    if email.casefold() not in addresses:
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

    @app.context_processor
    def _customer_mail_context():
        return {
            "office_mail_customer": match_customer,
            "office_customer_primary_email": primary_email,
            "office_customer_mail_history": mail_history,
        }
