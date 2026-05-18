import json
import os
import re
import time
from datetime import datetime, timezone
from urllib.error import URLError
from urllib.parse import urlencode, urlsplit, urlunsplit
from urllib.request import Request, urlopen

from flask import Flask, Response, abort, jsonify, redirect, render_template, request, send_from_directory

try:
    import awsgi
except ImportError:
    awsgi = None

from analytics import init_analytics
from config import config_dict
from notifications import explain_delivery_error, init_notifications, send_contact_emails


EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
VISIBLE_TEXT_PATTERN = re.compile(r"[A-Za-z]")
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


def _contact_template_context(app):
    return {
        "contact_turnstile_site_key": app.config.get("CONTACT_TURNSTILE_SITE_KEY", ""),
        "contact_min_submit_seconds": app.config.get("CONTACT_MIN_SUBMIT_SECONDS", 3),
    }


def _single_run_too_long(value, threshold):
    chunks = re.findall(r"[A-Za-z0-9]+", value or "")
    return any(len(chunk) >= threshold for chunk in chunks)


def _looks_like_spam_submission(name, message):
    normalized_name = " ".join((name or "").split())
    normalized_message = " ".join((message or "").split())
    message_words = re.findall(r"[A-Za-z]{2,}", normalized_message)

    if len(normalized_name) > 80 or len(normalized_message) > 4000:
        return True
    if len(normalized_name) < 2 or len(normalized_message) < 12:
        return True
    if not VISIBLE_TEXT_PATTERN.search(normalized_name) or not VISIBLE_TEXT_PATTERN.search(normalized_message):
        return True
    if " " not in normalized_message and _single_run_too_long(normalized_message, 20):
        return True
    if len(message_words) < 3 and _single_run_too_long(normalized_message, 16):
        return True
    if " " not in normalized_name and _single_run_too_long(normalized_name, 18):
        return True
    return False


def _verify_turnstile(app, token):
    secret_key = app.config.get("CONTACT_TURNSTILE_SECRET_KEY", "")
    if not secret_key:
        return True, None
    if not token:
        return False, "Complete the security check before sending your message."

    payload = urlencode(
        {
            "secret": secret_key,
            "response": token,
            "remoteip": request.headers.get("X-Forwarded-For", request.remote_addr or ""),
        }
    ).encode("utf-8")
    siteverify_request = Request(
        "https://challenges.cloudflare.com/turnstile/v0/siteverify",
        data=payload,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )

    try:
        with urlopen(siteverify_request, timeout=5) as response:
            verification = json.loads(response.read().decode("utf-8"))
    except (URLError, TimeoutError, ValueError) as exc:
        app.logger.warning("Turnstile verification failed: %s", exc)
        return False, "Security verification is temporarily unavailable. Please try again."

    if verification.get("success"):
        return True, None

    app.logger.info("Turnstile rejected contact submission: %s", verification.get("error-codes", []))
    return False, "Security verification failed. Please refresh the page and try again."


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
        elif request.path.startswith("/api/") or request.path in {"/admin", "/analytics"}:
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
        if page == "contact":
            return render_template(filename, **_contact_template_context(app))
        return render_template(filename)

    @app.route("/assets/<path:filename>")
    def assets(filename):
        return send_from_directory(os.path.join(app.root_path, "assets"), filename)

    @app.route("/admin")
    def admin_dashboard_redirect():
        return redirect("/analytics", code=301)

    @app.route("/analytics")
    def analytics_dashboard():
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
                "Disallow: /analytics",
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
        website = (payload.get("website") or "").strip()
        turnstile_token = (payload.get("turnstileToken") or payload.get("cf-turnstile-response") or "").strip()

        try:
            started_at = int(payload.get("startedAt") or 0)
        except (TypeError, ValueError):
            started_at = 0

        if website:
            app.logger.info("Blocked contact submission via honeypot from %s", request.headers.get("X-Forwarded-For", request.remote_addr))
            return jsonify({"message": "Message rejected."}), 400

        if not name or not sender or not message:
            return jsonify({"message": "name, email, and message are required."}), 400

        now = int(time.time())
        min_seconds = max(app.config.get("CONTACT_MIN_SUBMIT_SECONDS", 3), 0)
        max_seconds = max(app.config.get("CONTACT_MAX_SUBMIT_SECONDS", 60 * 60 * 2), min_seconds + 1)
        elapsed_seconds = now - started_at

        if not started_at or elapsed_seconds < min_seconds or elapsed_seconds > max_seconds:
            return jsonify({"message": "Please reload the page and try again."}), 400

        if not EMAIL_PATTERN.match(sender):
            return jsonify({"message": "Provide a valid email address."}), 400

        if _looks_like_spam_submission(name, message):
            app.logger.info("Rejected suspicious contact submission from %s", sender)
            return jsonify({"message": "Message rejected. Please provide a clearer message."}), 400

        turnstile_ok, turnstile_error = _verify_turnstile(app, turnstile_token)
        if not turnstile_ok:
            return jsonify({"message": turnstile_error}), 400

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