from __future__ import annotations

import imaplib
import mimetypes
import os
import re
import smtplib
import ssl
import time
from email import policy
from email.header import decode_header, make_header
from email.message import EmailMessage, Message
from email.parser import BytesParser
from email.utils import formataddr, getaddresses, parsedate_to_datetime
from html.parser import HTMLParser
from io import BytesIO

from flask import (
    abort,
    flash,
    redirect,
    render_template,
    request,
    send_file,
    url_for,
)
from werkzeug.utils import secure_filename


OFFICE_PREFIX = "/office"
MAIL_ADDRESS = os.environ.get("OFFICE_MAIL_ADDRESS", "").strip()
MAIL_PASSWORD = os.environ.get("OFFICE_MAIL_PASSWORD", "")
MAIL_DISPLAY_NAME = os.environ.get("OFFICE_MAIL_DISPLAY_NAME", "PZ-Med").strip() or "PZ-Med"
IMAP_HOST = os.environ.get("OFFICE_MAIL_IMAP_HOST", "mail.jino.ru").strip() or "mail.jino.ru"
IMAP_PORT = int(os.environ.get("OFFICE_MAIL_IMAP_PORT", "993"))
SMTP_HOST = os.environ.get("OFFICE_MAIL_SMTP_HOST", "smtp.jino.ru").strip() or "smtp.jino.ru"
SMTP_PORT = int(os.environ.get("OFFICE_MAIL_SMTP_PORT", "465"))
MAIL_PAGE_SIZE = max(10, min(int(os.environ.get("OFFICE_MAIL_PAGE_SIZE", "40")), 100))
MAIL_MAX_ATTACHMENT_BYTES = max(
    1,
    min(int(os.environ.get("OFFICE_MAIL_MAX_ATTACHMENT_MB", "10")), 20),
) * 1024 * 1024

_ADDRESS_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
_LIST_RE = re.compile(rb"\((?P<flags>[^)]*)\)\s+\"[^\"]*\"\s+(?P<name>.+)$")


class MailError(RuntimeError):
    pass


class MailConfigurationError(MailError):
    pass


class _HTMLTextExtractor(HTMLParser):
    BREAK_TAGS = {"br", "p", "div", "li", "tr", "table", "h1", "h2", "h3", "h4"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag.lower() in self.BREAK_TAGS:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() in self.BREAK_TAGS:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        self.parts.append(data)

    def text(self) -> str:
        value = "".join(self.parts).replace("\r", "")
        value = re.sub(r"[ \t]+\n", "\n", value)
        value = re.sub(r"\n{3,}", "\n\n", value)
        return value.strip()


def _configured() -> bool:
    return bool(MAIL_ADDRESS and MAIL_PASSWORD)


def _require_configured() -> None:
    if not _configured():
        raise MailConfigurationError(
            "Почта Office ещё не настроена на сервере. "
            "Добавьте OFFICE_MAIL_ADDRESS и OFFICE_MAIL_PASSWORD в /etc/pz-med-office.env."
        )


def _decode_header(value: str | None) -> str:
    if not value:
        return ""
    try:
        return str(make_header(decode_header(value)))
    except Exception:
        return value


def _format_date(value: str | None) -> str:
    if not value:
        return "—"
    try:
        parsed = parsedate_to_datetime(value)
        if parsed.tzinfo is not None:
            parsed = parsed.astimezone()
        return parsed.strftime("%d.%m.%Y %H:%M")
    except Exception:
        return value


def _folder_name_from_list(row: bytes) -> tuple[set[str], str] | None:
    match = _LIST_RE.match(row.strip())
    if not match:
        return None
    flags = {
        item.decode("ascii", errors="ignore").lower()
        for item in match.group("flags").split()
    }
    raw_name = match.group("name").strip()
    if raw_name.startswith(b'"') and raw_name.endswith(b'"'):
        raw_name = raw_name[1:-1].replace(b'\\"', b'"').replace(b'\\\\', b'\\')
    try:
        name = raw_name.decode("utf-8")
    except UnicodeDecodeError:
        name = raw_name.decode("ascii", errors="replace")
    return flags, name


def _imap() -> imaplib.IMAP4_SSL:
    _require_configured()
    try:
        client = imaplib.IMAP4_SSL(
            IMAP_HOST,
            IMAP_PORT,
            ssl_context=ssl.create_default_context(),
            timeout=15,
        )
        client.login(MAIL_ADDRESS, MAIL_PASSWORD)
        return client
    except Exception as error:
        raise MailError(f"Не удалось подключиться к почте через IMAP: {error}") from error


def _mailboxes(client: imaplib.IMAP4_SSL) -> dict[str, str]:
    result = {"inbox": "INBOX"}
    try:
        status, rows = client.list()
        if status != "OK" or not rows:
            return result
        parsed = [item for row in rows if row for item in [_folder_name_from_list(row)] if item]
        for flags, name in parsed:
            if "\\sent" in flags:
                result["sent"] = name
            elif "\\drafts" in flags:
                result["drafts"] = name
            elif "\\trash" in flags:
                result["trash"] = name
            elif "\\junk" in flags:
                result["junk"] = name

        lower_names = {name.lower(): name for _flags, name in parsed}
        if "sent" not in result:
            for candidate in ("sent", "sent items", "отправленные"):
                if candidate in lower_names:
                    result["sent"] = lower_names[candidate]
                    break
        if "drafts" not in result and "drafts" in lower_names:
            result["drafts"] = lower_names["drafts"]
        if "trash" not in result:
            for candidate in ("trash", "deleted", "deleted items"):
                if candidate in lower_names:
                    result["trash"] = lower_names[candidate]
                    break
        if "junk" not in result:
            for candidate in ("junk", "spam"):
                if candidate in lower_names:
                    result["junk"] = lower_names[candidate]
                    break
    except Exception:
        pass
    return result


def _logical_folder(client: imaplib.IMAP4_SSL, logical: str) -> str:
    folders = _mailboxes(client)
    if logical not in folders:
        raise MailError("Эта почтовая папка недоступна на сервере.")
    return folders[logical]


def _select(client: imaplib.IMAP4_SSL, logical: str, *, readonly: bool = False) -> str:
    mailbox = _logical_folder(client, logical)
    status, _data = client.select(mailbox, readonly=readonly)
    if status != "OK":
        raise MailError("Не удалось открыть почтовую папку.")
    return mailbox


def _parse_headers(raw: bytes, uid: str, flags_blob: bytes = b"") -> dict[str, object]:
    message = BytesParser(policy=policy.default).parsebytes(raw, headersonly=True)
    from_name, from_address = _first_address(message.get("From", ""))
    to_items = _format_addresses(message.get_all("To", []))
    return {
        "uid": uid,
        "subject": _decode_header(message.get("Subject")) or "Без темы",
        "from_name": from_name,
        "from_address": from_address,
        "from_display": from_name or from_address or "Неизвестный отправитель",
        "to_display": to_items,
        "date": _format_date(message.get("Date")),
        "message_id": (message.get("Message-ID") or "").strip(),
        "unread": b"\\Seen" not in flags_blob,
    }


def _first_address(value: str) -> tuple[str, str]:
    items = getaddresses([value])
    if not items:
        return "", ""
    name, address = items[0]
    return _decode_header(name), address.strip()


def _format_addresses(values: list[str]) -> str:
    parts = []
    for name, address in getaddresses(values):
        name = _decode_header(name)
        address = address.strip()
        if name and address:
            parts.append(f"{name} <{address}>")
        elif address:
            parts.append(address)
    return ", ".join(parts)


def _part_text(part: Message) -> str:
    try:
        content = part.get_content()
        if isinstance(content, str):
            return content
    except Exception:
        pass
    payload = part.get_payload(decode=True) or b""
    charset = part.get_content_charset() or "utf-8"
    try:
        return payload.decode(charset, errors="replace")
    except LookupError:
        return payload.decode("utf-8", errors="replace")


def _message_body(message: Message) -> str:
    plain_parts: list[str] = []
    html_parts: list[str] = []
    if message.is_multipart():
        for part in message.walk():
            if part.is_multipart():
                continue
            if part.get_content_disposition() == "attachment" or part.get_filename():
                continue
            content_type = part.get_content_type()
            if content_type == "text/plain":
                plain_parts.append(_part_text(part))
            elif content_type == "text/html":
                html_parts.append(_part_text(part))
    else:
        content_type = message.get_content_type()
        if content_type == "text/plain":
            plain_parts.append(_part_text(message))
        elif content_type == "text/html":
            html_parts.append(_part_text(message))

    text = "\n\n".join(item.strip() for item in plain_parts if item.strip())
    if not text and html_parts:
        extractor = _HTMLTextExtractor()
        extractor.feed("\n".join(html_parts))
        text = extractor.text()
    return text[:300_000].strip() or "В письме нет текстовой части."


def _attachments(message: Message) -> list[dict[str, object]]:
    items = []
    index = 0
    for part in message.walk():
        if part.is_multipart():
            continue
        filename = part.get_filename()
        disposition = part.get_content_disposition()
        if disposition != "attachment" and not filename:
            continue
        payload = part.get_payload(decode=True) or b""
        items.append(
            {
                "index": index,
                "filename": _decode_header(filename) if filename else f"attachment-{index + 1}",
                "content_type": part.get_content_type(),
                "size": len(payload),
            }
        )
        index += 1
    return items


def _fetch_message(logical: str, uid: str, *, mark_seen: bool) -> Message:
    if not uid.isdigit():
        abort(404)
    client = _imap()
    try:
        _select(client, logical, readonly=not mark_seen)
        query = "(RFC822)" if mark_seen else "(BODY.PEEK[])"
        status, data = client.uid("fetch", uid, query)
        if status != "OK" or not data:
            abort(404)
        raw = next((item[1] for item in data if isinstance(item, tuple) and item[1]), None)
        if not raw:
            abort(404)
        return BytesParser(policy=policy.default).parsebytes(raw)
    finally:
        try:
            client.logout()
        except Exception:
            pass


def _list_messages(logical: str, search: str) -> tuple[list[dict[str, object]], int, dict[str, str]]:
    client = _imap()
    try:
        _select(client, logical, readonly=True)
        status, data = client.uid("search", None, "ALL")
        if status != "OK":
            raise MailError("Не удалось получить список писем.")
        uids = (data[0] or b"").split()
        uids = list(reversed(uids[-max(MAIL_PAGE_SIZE * 3, 80):]))
        messages: list[dict[str, object]] = []
        search_lower = search.casefold()
        unread_count = 0
        for raw_uid in uids:
            uid = raw_uid.decode("ascii", errors="ignore")
            status, fetched = client.uid(
                "fetch",
                uid,
                "(BODY.PEEK[HEADER.FIELDS (FROM TO SUBJECT DATE MESSAGE-ID)] FLAGS)",
            )
            if status != "OK" or not fetched:
                continue
            tuple_item = next((item for item in fetched if isinstance(item, tuple)), None)
            if not tuple_item:
                continue
            flags_blob = tuple_item[0] if isinstance(tuple_item[0], bytes) else b""
            item = _parse_headers(tuple_item[1], uid, flags_blob)
            if item["unread"]:
                unread_count += 1
            if search_lower:
                haystack = " ".join(
                    str(item.get(key) or "")
                    for key in ("subject", "from_name", "from_address", "to_display")
                ).casefold()
                if search_lower not in haystack:
                    continue
            messages.append(item)
            if len(messages) >= MAIL_PAGE_SIZE:
                break
        return messages, unread_count, _mailboxes(client)
    finally:
        try:
            client.logout()
        except Exception:
            pass


def _parse_recipients(raw: str, field_name: str) -> list[str]:
    raw = (raw or "").replace(";", ",").strip()
    if not raw:
        return []
    result: list[str] = []
    for _name, address in getaddresses([raw]):
        address = address.strip()
        if not address or not _ADDRESS_RE.fullmatch(address):
            raise ValueError(f"Некорректный адрес в поле «{field_name}».")
        lowered = address.casefold()
        if lowered not in {item.casefold() for item in result}:
            result.append(address)
    if len(result) > 20:
        raise ValueError(f"В поле «{field_name}» можно указать не более 20 адресов.")
    return result


def _smtp_send(message: EmailMessage, recipients: list[str]) -> None:
    _require_configured()
    context = ssl.create_default_context()
    try:
        if SMTP_PORT == 465:
            with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, timeout=20, context=context) as client:
                client.login(MAIL_ADDRESS, MAIL_PASSWORD)
                client.send_message(message, from_addr=MAIL_ADDRESS, to_addrs=recipients)
        else:
            with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=20) as client:
                client.ehlo()
                client.starttls(context=context)
                client.ehlo()
                client.login(MAIL_ADDRESS, MAIL_PASSWORD)
                client.send_message(message, from_addr=MAIL_ADDRESS, to_addrs=recipients)
    except Exception as error:
        raise MailError(f"Не удалось отправить письмо через SMTP: {error}") from error


def _append_to_sent(message: EmailMessage) -> None:
    try:
        client = _imap()
        try:
            mailbox = _mailboxes(client).get("sent")
            if not mailbox:
                return
            client.append(mailbox, "\\Seen", imaplib.Time2Internaldate(time.time()), message.as_bytes())
        finally:
            client.logout()
    except Exception:
        # Письмо уже принято SMTP-сервером. Ошибка копирования в Sent не должна
        # превращать успешную отправку в ложную ошибку для пользователя.
        return


def _reply_context(folder: str, uid: str) -> dict[str, str]:
    message = _fetch_message(folder, uid, mark_seen=False)
    reply_source = message.get("Reply-To") or message.get("From") or ""
    _name, address = _first_address(reply_source)
    subject = _decode_header(message.get("Subject"))
    if subject and not subject.lower().startswith("re:"):
        subject = f"Re: {subject}"
    elif not subject:
        subject = "Re:"
    body = _message_body(message)
    quoted = "\n".join(f"> {line}" if line else ">" for line in body.splitlines())
    references = (message.get("References") or "").strip()
    message_id = (message.get("Message-ID") or "").strip()
    if message_id and message_id not in references:
        references = f"{references} {message_id}".strip()
    return {
        "to": address,
        "subject": subject,
        "body": f"\n\n--- Исходное письмо ---\n{quoted}"[:120_000],
        "in_reply_to": message_id,
        "references": references,
    }


def _folder_label(logical: str) -> str:
    return {
        "inbox": "Входящие",
        "sent": "Отправленные",
        "drafts": "Черновики",
        "trash": "Корзина",
        "junk": "Спам",
    }.get(logical, logical)


def register_mail_features(app, *, login_required) -> None:
    @app.get(f"{OFFICE_PREFIX}/mail")
    @login_required
    def mail_inbox():
        folder = (request.args.get("folder") or "inbox").strip().lower()
        search = (request.args.get("q") or "").strip()
        if folder not in {"inbox", "sent", "drafts", "trash", "junk"}:
            abort(404)

        if not _configured():
            return render_template(
                "mail_inbox.html",
                mail_configured=False,
                mail_address=MAIL_ADDRESS,
                messages=[],
                mailboxes={"inbox": "INBOX"},
                folder="inbox",
                folder_label="Входящие",
                search=search,
                unread_count=0,
            )

        try:
            messages, unread_count, mailboxes = _list_messages(folder, search)
        except MailError as error:
            flash(str(error), "error")
            messages, unread_count, mailboxes = [], 0, {"inbox": "INBOX"}

        return render_template(
            "mail_inbox.html",
            mail_configured=True,
            mail_address=MAIL_ADDRESS,
            messages=messages,
            mailboxes=mailboxes,
            folder=folder,
            folder_label=_folder_label(folder),
            search=search,
            unread_count=unread_count,
        )

    @app.get(f"{OFFICE_PREFIX}/mail/message/<uid>")
    @login_required
    def mail_message(uid: str):
        folder = (request.args.get("folder") or "inbox").strip().lower()
        if folder not in {"inbox", "sent", "drafts", "trash", "junk"}:
            abort(404)
        try:
            message = _fetch_message(folder, uid, mark_seen=(folder == "inbox"))
        except MailError as error:
            flash(str(error), "error")
            return redirect(url_for("mail_inbox", folder=folder))

        from_name, from_address = _first_address(message.get("From", ""))
        return render_template(
            "mail_message.html",
            folder=folder,
            folder_label=_folder_label(folder),
            uid=uid,
            subject=_decode_header(message.get("Subject")) or "Без темы",
            from_name=from_name,
            from_address=from_address,
            to_display=_format_addresses(message.get_all("To", [])),
            cc_display=_format_addresses(message.get_all("Cc", [])),
            date_display=_format_date(message.get("Date")),
            body=_message_body(message),
            attachments=_attachments(message),
        )

    @app.get(f"{OFFICE_PREFIX}/mail/message/<uid>/attachment/<int:index>")
    @login_required
    def mail_attachment(uid: str, index: int):
        folder = (request.args.get("folder") or "inbox").strip().lower()
        if folder not in {"inbox", "sent", "drafts", "trash", "junk"}:
            abort(404)
        try:
            message = _fetch_message(folder, uid, mark_seen=False)
        except MailError as error:
            flash(str(error), "error")
            return redirect(url_for("mail_inbox", folder=folder))

        attachment_index = 0
        for part in message.walk():
            if part.is_multipart():
                continue
            filename = part.get_filename()
            disposition = part.get_content_disposition()
            if disposition != "attachment" and not filename:
                continue
            if attachment_index == index:
                payload = part.get_payload(decode=True) or b""
                if len(payload) > MAIL_MAX_ATTACHMENT_BYTES:
                    abort(413)
                filename = _decode_header(filename) if filename else f"attachment-{index + 1}"
                safe_name = secure_filename(filename) or f"attachment-{index + 1}"
                return send_file(
                    BytesIO(payload),
                    as_attachment=True,
                    download_name=safe_name,
                    mimetype=part.get_content_type(),
                    max_age=0,
                )
            attachment_index += 1
        abort(404)

    @app.route(f"{OFFICE_PREFIX}/mail/compose", methods=["GET", "POST"])
    @login_required
    def mail_compose():
        if not _configured():
            flash("Сначала настройте почтовый ящик Office на сервере.", "error")
            return redirect(url_for("mail_inbox"))

        form_data = {
            "to": (request.args.get("to") or "").strip(),
            "cc": "",
            "subject": (request.args.get("subject") or "").strip(),
            "body": "",
            "in_reply_to": "",
            "references": "",
        }
        reply_uid = (request.args.get("reply_uid") or "").strip()
        reply_folder = (request.args.get("reply_folder") or "inbox").strip().lower()
        if request.method == "GET" and reply_uid:
            try:
                form_data.update(_reply_context(reply_folder, reply_uid))
            except MailError as error:
                flash(str(error), "error")

        if request.method == "POST":
            form_data = {
                "to": (request.form.get("to") or "").strip(),
                "cc": (request.form.get("cc") or "").strip(),
                "subject": (request.form.get("subject") or "").strip(),
                "body": request.form.get("body") or "",
                "in_reply_to": (request.form.get("in_reply_to") or "").strip(),
                "references": (request.form.get("references") or "").strip(),
            }
            try:
                to_addresses = _parse_recipients(form_data["to"], "Кому")
                cc_addresses = _parse_recipients(form_data["cc"], "Копия")
                if not to_addresses:
                    raise ValueError("Укажите хотя бы одного получателя.")
                if not form_data["subject"]:
                    raise ValueError("Укажите тему письма.")
                if len(form_data["subject"]) > 300:
                    raise ValueError("Тема письма слишком длинная.")
                if len(form_data["body"]) > 300_000:
                    raise ValueError("Текст письма слишком большой.")

                message = EmailMessage(policy=policy.SMTP)
                message["From"] = formataddr((MAIL_DISPLAY_NAME, MAIL_ADDRESS))
                message["To"] = ", ".join(to_addresses)
                if cc_addresses:
                    message["Cc"] = ", ".join(cc_addresses)
                message["Subject"] = form_data["subject"]
                if form_data["in_reply_to"]:
                    message["In-Reply-To"] = form_data["in_reply_to"]
                if form_data["references"]:
                    message["References"] = form_data["references"]
                message.set_content(form_data["body"] or " ", subtype="plain", charset="utf-8")

                total_attachment_bytes = 0
                files = [item for item in request.files.getlist("attachments") if item and item.filename]
                if len(files) > 5:
                    raise ValueError("Можно приложить не более 5 файлов к одному письму.")
                for item in files:
                    data = item.read(MAIL_MAX_ATTACHMENT_BYTES + 1)
                    total_attachment_bytes += len(data)
                    if total_attachment_bytes > MAIL_MAX_ATTACHMENT_BYTES:
                        raise ValueError("Общий размер вложений превышает допустимый лимит.")
                    filename = secure_filename(item.filename) or "attachment"
                    guessed_type = item.mimetype or mimetypes.guess_type(filename)[0] or "application/octet-stream"
                    maintype, subtype = guessed_type.split("/", 1)
                    message.add_attachment(data, maintype=maintype, subtype=subtype, filename=filename)

                recipients = to_addresses + [item for item in cc_addresses if item not in to_addresses]
                _smtp_send(message, recipients)
                _append_to_sent(message)
                flash("Письмо отправлено.", "success")
                return redirect(url_for("mail_inbox", folder="sent"))
            except (ValueError, MailError) as error:
                flash(str(error), "error")

        return render_template(
            "mail_compose.html",
            mail_address=MAIL_ADDRESS,
            form_data=form_data,
            max_attachment_mb=MAIL_MAX_ATTACHMENT_BYTES // (1024 * 1024),
        )
