from __future__ import annotations

import os
from pathlib import Path

import office_app
from office_release import register_release_features


app = office_app.app
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
