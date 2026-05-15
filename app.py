import os
import re
from datetime import datetime, timezone
from urllib.parse import urlsplit, urlunsplit

from flask import Flask, Response, abort, jsonify, redirect, render_template, request, send_from_directory

try:
    import awsgi
except ImportError:
    awsgi = None

from analytics import init_analytics
from config import config_dict
from notifications import explain_delivery_error, init_notifications, send_contact_emails


EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
PAGE_FILES = {
    "": "index.html",
    "about": "about.html",
    "experience": "experience.html",
    "ml-ai-full-stack-engineer-aws-azure": "ml-ai-full-stack-engineer-aws-azure.html",
    "projects": "projects.html",
    "research": "research.html",
    "contact": "contact.html",
}
PAGE_SITEMAP_METADATA = {
    "": {"lastmod": "2026-05-16", "changefreq": "weekly", "priority": "1.0"},
    "about": {"lastmod": "2026-05-16", "changefreq": "monthly", "priority": "0.8"},
    "experience": {"lastmod": "2026-05-16", "changefreq": "monthly", "priority": "0.9"},
    "ml-ai-full-stack-engineer-aws-azure": {"lastmod": "2026-05-16", "changefreq": "weekly", "priority": "0.9"},
    "projects": {"lastmod": "2026-05-16", "changefreq": "weekly", "priority": "0.9"},
    "research": {"lastmod": "2026-05-16", "changefreq": "monthly", "priority": "0.7"},
    "contact": {"lastmod": "2026-05-16", "changefreq": "monthly", "priority": "0.6"},
}


def _normalize_base_url(base_url):
    return (base_url or "").rstrip("/")


def _page_url(base_url, slug):
    if not slug:
        return f"{base_url}/"
    return f"{base_url}/{slug}"


def _preferred_host(base_url):
    return urlsplit(base_url).netloc.lower()


def _redirect_to_canonical_host(base_url):
    preferred_parts = urlsplit(base_url)
    preferred_host = _preferred_host(base_url)
    if not preferred_host:
        return None

    request_host = (request.host or "").lower()
    if request_host == preferred_host or not request_host:
        return None

    if request_host == f"www.{preferred_host}":
        target = urlunsplit((preferred_parts.scheme or request.scheme, preferred_host, request.full_path.rstrip("?") or request.path, "", ""))
        return redirect(target, code=301)

    return None


def _format_timestamp(epoch_seconds):
    if not epoch_seconds:
        return "No data yet"
    return datetime.fromtimestamp(epoch_seconds, tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def create_app(config_name=None):
    if config_name is None:
        config_name = os.getenv("FLASK_ENV", "development")

    app = Flask(__name__)
    app.config.from_object(config_dict.get(config_name, config_dict["default"]))
    init_notifications(app)
    analytics = init_analytics(app)
    base_url = _normalize_base_url(app.config.get("APP_BASE_URL", ""))

    @app.before_request
    def enforce_canonical_host():
        redirect_response = _redirect_to_canonical_host(base_url)
        if redirect_response is not None:
            return redirect_response

    @app.after_request
    def add_cors_headers(response):
        response.headers["Access-Control-Allow-Origin"] = "*"
        response.headers["Access-Control-Allow-Headers"] = "Content-Type"
        response.headers["Access-Control-Allow-Methods"] = "OPTIONS,POST,GET"
        if request.path.startswith("/assets/"):
            response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
        elif request.path in {"/robots.txt", "/sitemap.xml"}:
            response.headers["Cache-Control"] = "public, max-age=3600"
        elif request.path.startswith("/api/") or request.path == "/admin":
            response.headers["Cache-Control"] = "no-store"
            response.headers["X-Robots-Tag"] = "noindex, nofollow"
        elif request.method == "GET" and response.status_code < 400:
            response.headers["Cache-Control"] = "public, max-age=300, s-maxage=3600"
        return analytics.record_response(response)

    @app.route("/")
    def index():
        return render_template("index.html")

    @app.route("/<page>")
    def page(page):
        filename = PAGE_FILES.get(page)
        if not filename:
            abort(404)
        return render_template(filename)

    @app.route("/assets/<path:filename>")
    def assets(filename):
        return send_from_directory(os.path.join(app.root_path, "assets"), filename)

    @app.route("/admin")
    def admin_dashboard():
        summary = analytics.summary_data()
        if summary is None:
            return render_template("admin.html", analytics_enabled=False, summary=None, format_timestamp=_format_timestamp)
        return render_template("admin.html", analytics_enabled=True, summary=summary, format_timestamp=_format_timestamp)

    @app.route("/robots.txt")
    def robots():
        robots_body = "\n".join(
            [
                "User-agent: *",
                "Allow: /",
                "Disallow: /admin",
                f"Sitemap: {base_url}/sitemap.xml",
            ]
        )
        return Response(robots_body, mimetype="text/plain")

    @app.route("/sitemap.xml")
    def sitemap():
        xml_lines = [
            '<?xml version="1.0" encoding="UTF-8"?>',
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">',
        ]

        for slug in PAGE_FILES:
            url = _page_url(base_url, slug)
            metadata = PAGE_SITEMAP_METADATA.get(slug, {})
            xml_lines.extend(
                [
                    "  <url>",
                    f"    <loc>{url}</loc>",
                    f"    <lastmod>{metadata.get('lastmod', '2026-05-16')}</lastmod>",
                    f"    <changefreq>{metadata.get('changefreq', 'monthly')}</changefreq>",
                    f"    <priority>{metadata.get('priority', '0.7')}</priority>",
                    "  </url>",
                ]
            )

        xml_lines.append("</urlset>")
        return Response("\n".join(xml_lines), mimetype="application/xml")

    @app.route("/api/contact", methods=["OPTIONS", "POST"])
    def contact_api():
        if request.method == "OPTIONS":
            return ("", 204)

        payload = request.get_json(silent=True) or request.form.to_dict()
        name = (payload.get("name") or "").strip()
        sender = (payload.get("email") or "").strip()
        message = (payload.get("message") or "").strip()

        if not name or not sender or not message:
            return jsonify({"message": "name, email, and message are required."}), 400

        if not EMAIL_PATTERN.match(sender):
            return jsonify({"message": "Provide a valid email address."}), 400

        try:
            send_contact_emails(name, sender, message)
        except Exception as exc:
            return jsonify({"message": "Unable to send email.", "detail": explain_delivery_error(exc)}), 500

        return jsonify({"message": "Message accepted."})

    @app.route("/api/analytics/summary")
    def analytics_summary():
        return analytics.summary_response()

    return app


app = create_app()


def lambda_handler(event, context):
    if awsgi is None:
        raise RuntimeError("awsgi must be installed for Lambda deployment.")

    return awsgi.response(
        app,
        event,
        context,
        base64_content_types={
            "image/png",
            "image/jpeg",
            "image/webp",
            "image/gif",
            "image/x-icon",
            "video/mp4",
            "application/octet-stream",
        },
    )


if __name__ == "__main__":
    app.run(debug=app.config.get("DEBUG", False), host="127.0.0.1", port=5000)