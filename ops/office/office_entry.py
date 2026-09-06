from __future__ import annotations

import os
from pathlib import Path

import office_app
from office_customer_mail import register_customer_mail_features
from office_mail import register_mail_features
from office_mail_actions import register_mail_action_features
from office_release import register_release_features


app = office_app.app
# Почтовый модуль принимает до 10 МБ вложений плюс MIME-накладные расходы.
# Nginx ограничен тем же безопасным порядком величины в deploy_office.sh.
app.config["MAX_CONTENT_LENGTH"] = 12 * 1024 * 1024

register_release_features(
    app,
    db_path=office_app.DB_PATH,
    releases_dir=Path(
        os.environ.get(
            "OFFICE_RELEASES_DIR",
            "/var/lib/pz-med-office/releases",
        )
    ),
    get_db=office_app.get_db,
    login_required=office_app.login_required,
    customer_or_404=office_app._customer_or_404,
    now_iso=office_app._now_iso,
)
register_mail_features(
    app,
    login_required=office_app.login_required,
)
register_mail_action_features(
    app,
    login_required=office_app.login_required,
)
register_customer_mail_features(
    app,
    get_db=office_app.get_db,
)
