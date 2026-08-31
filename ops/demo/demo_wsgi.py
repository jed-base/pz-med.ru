from __future__ import annotations

import re

from flask import Response, jsonify, request
from flask_login import current_user, login_user
from werkzeug.middleware.proxy_fix import ProxyFix

from app import create_app
from app.models import User


DEMO_USERNAME = "demo_ivanov"

application = create_app()
application.config.update(
    PREFERRED_URL_SCHEME="https",
)
application.wsgi_app = ProxyFix(
    application.wsgi_app,
    x_for=1,
    x_proto=1,
    x_host=1,
)


def _blocked_change_response():
    message = (
        "Изменение системных настроек "
        "отключено в демонстрационной версии."
    )

    wants_json = (
        request.is_json
        or request.headers.get("X-Requested-With")
        == "XMLHttpRequest"
        or request.accept_mimetypes.best
        == "application/json"
    )

    if wants_json:
        return jsonify(
            ok=False,
            message=message,
        ), 403

    return Response(
        message,
        status=403,
        content_type="text/plain; charset=utf-8",
    )


@application.before_request
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

    # Смена личной цветовой темы безопасна и нужна для демонстрации UI.
    allowed_mutating_paths = {
        "/account/theme",
    }

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

        if (
            request.path not in allowed_mutating_paths
            and request.path.startswith(blocked_prefixes)
        ):
            return _blocked_change_response()

        if (request.content_type or "").lower().startswith(
            "multipart/form-data"
        ):
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
<div class="pz-demo-banner"><strong>Демонстрационная версия PZ-Med</strong><span>Все сотрудники и данные вымышлены. Изменения периодически сбрасываются.</span><a href="https://pz-med.ru/">Вернуться на сайт</a></div>
"""


_PREVIEW_STYLE = """
<style id="pz-demo-preview-style">
html{scrollbar-width:none}html::-webkit-scrollbar,body::-webkit-scrollbar{display:none}body{cursor:default}
a,button,[role="button"],[onclick],.dashboard-card,.dashboard-task-item,.dashboard-report-item,.dashboard-event,.dashboard-announcement-item{transition:box-shadow .16s ease,outline-color .16s ease,transform .16s ease,filter .16s ease!important}
a:hover,button:hover,[role="button"]:hover,[onclick]:hover,.dashboard-card:hover,.dashboard-task-item:hover,.dashboard-report-item:hover,.dashboard-event:hover,.dashboard-announcement-item:hover{cursor:pointer!important;outline:3px solid rgba(36,170,128,.72)!important;outline-offset:2px!important;box-shadow:0 10px 30px rgba(13,92,70,.18)!important;filter:saturate(1.08) brightness(1.015)!important;position:relative;z-index:20}
.dashboard-card:hover{transform:translateY(-2px)!important}
</style>
"""


_PREVIEW_SCRIPT = """
<script id="pz-demo-preview-script">
(() => {
  const demoRoot = 'https://demo.pz-med.ru/';

  const targetFor = (element) => {
    const link = element && element.closest ? element.closest('a[href]') : null;
    if (!link) return demoRoot;

    try {
      const url = new URL(link.href, window.location.href);
      if (url.origin !== window.location.origin) return demoRoot;
      url.searchParams.delete('preview');
      return url.href;
    } catch (_) {
      return demoRoot;
    }
  };

  document.addEventListener('click', (event) => {
    const target = targetFor(event.target);
    event.preventDefault();
    event.stopImmediatePropagation();
    window.open(target, '_top');
  }, true);

  document.addEventListener('submit', (event) => {
    event.preventDefault();
    event.stopImmediatePropagation();
    window.open(demoRoot, '_top');
  }, true);
})();
</script>
"""


@application.after_request
def _demo_response_headers(response):
    response.headers["X-Robots-Tag"] = "noindex, nofollow, noarchive"
    response.headers["Cache-Control"] = "no-store"

    preview_mode = request.args.get("preview") == "1"
    if preview_mode:
        # Разрешаем показывать специальный preview только на основном сайте.
        response.headers.pop("X-Frame-Options", None)
        response.headers["Content-Security-Policy"] = (
            "frame-ancestors 'self' https://pz-med.ru"
        )

    content_type = response.content_type or ""
    if response.status_code == 200 and content_type.startswith("text/html"):
        try:
            html = response.get_data(as_text=True)

            if preview_mode:
                if "pz-demo-preview-style" not in html:
                    html = html.replace(
                        "</head>",
                        _PREVIEW_STYLE + "</head>",
                        1,
                    )
                if "pz-demo-preview-script" not in html:
                    html = html.replace(
                        "</body>",
                        _PREVIEW_SCRIPT + "</body>",
                        1,
                    )
            elif "pz-demo-banner" not in html:
                html = html.replace("</head>", _BANNER_STYLE + "</head>", 1)
                html = re.sub(r"(<body[^>]*>)", r"\1" + _BANNER, html, count=1)

            response.set_data(html)
            response.headers.pop("Content-Length", None)
        except Exception:
            pass
    return response
