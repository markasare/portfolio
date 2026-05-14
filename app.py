import os
import re

from flask import Flask, Response, abort, jsonify, request, send_from_directory

try:
    import awsgi
except ImportError:
    awsgi = None

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


def _normalize_base_url(base_url):
    return (base_url or "").rstrip("/")


def _page_url(base_url, slug):
    if not slug:
        return f"{base_url}/"
    return f"{base_url}/{slug}"


def create_app(config_name=None):
    if config_name is None:
        config_name = os.getenv("FLASK_ENV", "development")

    app = Flask(__name__)
    app.config.from_object(config_dict.get(config_name, config_dict["default"]))
    init_notifications(app)
    base_url = _normalize_base_url(app.config.get("APP_BASE_URL", ""))

    @app.after_request
    def add_cors_headers(response):
        response.headers["Access-Control-Allow-Origin"] = "*"
        response.headers["Access-Control-Allow-Headers"] = "Content-Type"
        response.headers["Access-Control-Allow-Methods"] = "OPTIONS,POST,GET"
        return response

    @app.route("/")
    def index():
        return send_from_directory(app.root_path, "index.html")

    @app.route("/<page>")
    def page(page):
        filename = PAGE_FILES.get(page)
        if not filename:
            abort(404)
        return send_from_directory(app.root_path, filename)

    @app.route("/assets/<path:filename>")
    def assets(filename):
        return send_from_directory(os.path.join(app.root_path, "assets"), filename)

    @app.route("/robots.txt")
    def robots():
        robots_body = "\n".join(
            [
                "User-agent: *",
                "Allow: /",
                f"Sitemap: {base_url}/sitemap.xml",
            ]
        )
        return Response(robots_body, mimetype="text/plain")

    @app.route("/sitemap.xml")
    def sitemap():
        urls = [_page_url(base_url, slug) for slug in PAGE_FILES]
        xml_lines = [
            '<?xml version="1.0" encoding="UTF-8"?>',
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">',
        ]

        for url in urls:
            xml_lines.extend(["  <url>", f"    <loc>{url}</loc>", "  </url>"])

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