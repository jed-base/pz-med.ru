from __future__ import annotations

from flask import abort, flash, redirect, request, url_for

from office_mail import MailError, _imap, _mailboxes, _select


OFFICE_PREFIX = "/office"
_ALLOWED_FOLDERS = {"inbox", "sent", "drafts", "trash", "junk"}


def _validated(folder: str, uid: str) -> tuple[str, str]:
    folder = (folder or "inbox").strip().lower()
    if folder not in _ALLOWED_FOLDERS or not uid.isdigit():
        abort(404)
    return folder, uid


def _close(client) -> None:
    try:
        client.logout()
    except Exception:
        pass


def _set_seen(folder: str, uid: str, *, seen: bool) -> None:
    client = _imap()
    try:
        _select(client, folder, readonly=False)
        operation = "+FLAGS.SILENT" if seen else "-FLAGS.SILENT"
        status, _data = client.uid("STORE", uid, operation, "(\\Seen)")
        if status != "OK":
            raise MailError("Не удалось изменить статус письма.")
    finally:
        _close(client)


def _move_to_trash(folder: str, uid: str) -> None:
    client = _imap()
    try:
        _select(client, folder, readonly=False)
        trash = _mailboxes(client).get("trash")
        if not trash:
            raise MailError("На почтовом сервере не найдена папка «Корзина».")

        # RFC 6851 MOVE — основной вариант. Для серверов без MOVE ниже есть
        # совместимый fallback COPY + \\Deleted + EXPUNGE.
        status, _data = client.uid("MOVE", uid, trash)
        if status == "OK":
            return

        status, _data = client.uid("COPY", uid, trash)
        if status != "OK":
            raise MailError("Не удалось переместить письмо в корзину.")
        status, _data = client.uid("STORE", uid, "+FLAGS.SILENT", "(\\Deleted)")
        if status != "OK":
            raise MailError("Письмо скопировано в корзину, но не удалось удалить исходную копию.")
        client.expunge()
    finally:
        _close(client)


def _delete_forever(uid: str) -> None:
    client = _imap()
    try:
        _select(client, "trash", readonly=False)
        status, _data = client.uid("STORE", uid, "+FLAGS.SILENT", "(\\Deleted)")
        if status != "OK":
            raise MailError("Не удалось удалить письмо.")
        status, _data = client.expunge()
        if status != "OK":
            raise MailError("Почтовый сервер не подтвердил окончательное удаление письма.")
    finally:
        _close(client)


def register_mail_action_features(app, *, login_required) -> None:
    @app.post(f"{OFFICE_PREFIX}/mail/message/<uid>/status")
    @login_required
    def mail_message_status(uid: str):
        folder, uid = _validated(request.form.get("folder", "inbox"), uid)
        action = (request.form.get("action") or "").strip().lower()
        if action not in {"read", "unread"}:
            abort(400)
        try:
            _set_seen(folder, uid, seen=(action == "read"))
            flash(
                "Письмо отмечено как прочитанное."
                if action == "read"
                else "Письмо отмечено как непрочитанное.",
                "success",
            )
        except MailError as error:
            flash(str(error), "error")
        return redirect(url_for("mail_inbox", folder=folder))

    @app.post(f"{OFFICE_PREFIX}/mail/message/<uid>/delete")
    @login_required
    def mail_message_delete(uid: str):
        folder, uid = _validated(request.form.get("folder", "inbox"), uid)
        try:
            if folder == "trash":
                _delete_forever(uid)
                flash("Письмо удалено окончательно.", "success")
            else:
                _move_to_trash(folder, uid)
                flash("Письмо перемещено в корзину.", "success")
        except MailError as error:
            flash(str(error), "error")
        return redirect(url_for("mail_inbox", folder=folder if folder == "trash" else "inbox"))
