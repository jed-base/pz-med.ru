from __future__ import annotations

import re

from flask import Response, request
from flask_login import current_user, login_user
from werkzeug.middleware.dispatcher import DispatcherMiddleware
from werkzeug.middleware.proxy_fix import ProxyFix

from app import create_app
from app.models import User


DEMO_USERNAME = "demo_ivanov"

clinic_app = create_app()
clinic_app.config.update(
    APPLICATION_ROOT="/demo",
    SESSION_COOKIE_PATH="/demo",
    PREFERRED_URL_SCHEME="https",
)
clinic_app.wsgi_app = ProxyFix(
    clinic_app.wsgi_app,
    x_for=1,
    x_proto=1,
    x_host=1,
)


@clinic_app.before_request
def _demo_auto_login_and_guard():
    user = User.query.filter_by(username=DEMO_USERNAME).first()
    if user is None:
        return Response(
            "Демонстрационная база ещё не подготовлена.",
            status=503,
            content_type="text/plain; charset=utf-8",
        )

    if not current_user.is_authenticated:
        login_user(user, remember=False, force=True)

    # В публичной песочнице разрешаем обычные рабочие сценарии,
    # но не даём менять структуру/пользователей/системные настройки.
    if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
        blocked_prefixes = (
            "/admin",
            "/users",
            "/clinic-settings",
            "/subdivisions",
            "/departments",
            "/positions",
            "/employees",
            "/assignments",
            "/certificates",
            "/account",
        )
        if request.path.startswith(blocked_prefixes):
            return Response(
                "Изменение системных настроек отключено в демонстрационной версии.",
                status=403,
                content_type="text/plain; charset=utf-8",
            )

        if (request.content_type or "").lower().startswith("multipart/form-data"):
            return Response(
                "Загрузка файлов отключена в публичной демонстрационной версии.",
                status=403,
                content_type="text/plain; charset=utf-8",
            )


_BANNER_STYLE = """
<style id="pz-demo-style">
.pz-demo-banner{position:sticky;top:0;z-index:99999;display:flex;gap:12px;align-items:center;justify-content:center;padding:8px 16px;background:#fff4cc;color:#4b3b00;border-bottom:1px solid #e7d58c;font:600 13px/1.35 system-ui,-apple-system,Segoe UI,sans-serif}.pz-demo-banner a{color:#0d5c46;font-weight:800;text-decoration:none}.pz-demo-banner strong{font-weight:800}
</style>
"""

_BANNER = """
<div class="pz-demo-banner"><strong>Демонстрационная версия PZ-Med</strong><span>Все сотрудники и данные вымышлены. Изменения периодически сбрасываются.</span><a href="/">Вернуться на сайт</a></div>
"""


@clinic_app.after_request
def _demo_response_headers(response):
    response.headers["X-Robots-Tag"] = "noindex, nofollow, noarchive"
    response.headers["Cache-Control"] = "no-store"

    if response.status_code == 200 and response.content_type.startswith("text/html"):
        try:
            html = response.get_data(as_text=True)
            if "pz-demo-banner" not in html:
                html = html.replace("</head>", _BANNER_STYLE + "</head>", 1)
                html = re.sub(r"(<body[^>]*>)", r"\1" + _BANNER, html, count=1)
                response.set_data(html)
                response.headers.pop("Content-Length", None)
        except Exception:
            pass
    return response


def _not_found(environ, start_response):
    response = Response("Not found", status=404)
    return response(environ, start_response)


application = DispatcherMiddleware(
    _not_found,
    {"/demo": clinic_app},
)
