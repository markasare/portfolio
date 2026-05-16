import hashlib
import time
import uuid

from flask import current_app, jsonify, request

try:
    import boto3
    from boto3.dynamodb.conditions import Key
except ImportError:
    boto3 = None
    Key = None


def _as_int(value, default):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _hash_ip(remote_addr):
    if not remote_addr:
        return ""
    return hashlib.sha256(remote_addr.encode("utf-8")).hexdigest()


def _hash_visitor_id(visitor_id):
    if not visitor_id:
        return ""
    return hashlib.sha256(visitor_id.encode("utf-8")).hexdigest()[:12]


def _normalize_country_code(value):
    country_code = (value or "").strip().upper()
    if len(country_code) != 2 or not country_code.isalpha():
        return "UNKNOWN"
    return country_code


def _country_name_from_headers():
    label = (
        request.headers.get("CloudFront-Viewer-Country-Name")
        or request.headers.get("X-Country-Name")
        or ""
    ).strip()
    return label[:80] or None


def _country_code_from_headers():
    return _normalize_country_code(
        request.headers.get("CloudFront-Viewer-Country")
        or request.headers.get("X-Country-Code")
        or request.headers.get("CF-IPCountry")
    )


def _city_from_headers():
    city = (
        request.headers.get("CloudFront-Viewer-City")
        or request.headers.get("X-City")
        or ""
    ).strip()
    return city[:80] or None


def _country_headers_snapshot():
    return {
        "cloudfront_city": (request.headers.get("CloudFront-Viewer-City") or "").strip()[:80],
        "cloudfront_country": (request.headers.get("CloudFront-Viewer-Country") or "").strip()[:8],
        "cloudfront_country_name": (request.headers.get("CloudFront-Viewer-Country-Name") or "").strip()[:80],
        "cf_ip_country": (request.headers.get("CF-IPCountry") or "").strip()[:8],
        "x_city": (request.headers.get("X-City") or "").strip()[:80],
        "x_country_code": (request.headers.get("X-Country-Code") or "").strip()[:8],
        "x_country_name": (request.headers.get("X-Country-Name") or "").strip()[:80],
    }


class AnalyticsTracker:
    def __init__(self, app=None):
        self.app = None
        self.table = None
        self.enabled = False

        if app is not None:
            self.init_app(app)

    def init_app(self, app):
        self.app = app
        self.enabled = False
        self.table = None

        table_name = (app.config.get("VISITOR_ANALYTICS_TABLE") or "").strip()
        if not table_name or boto3 is None:
            return self

        dynamodb = boto3.resource(
            "dynamodb",
            region_name=app.config.get("ANALYTICS_AWS_REGION", "us-west-2"),
            aws_access_key_id=app.config.get("AWS_ACCESS_KEY_ID") or None,
            aws_secret_access_key=app.config.get("AWS_SECRET_ACCESS_KEY") or None,
            aws_session_token=app.config.get("AWS_SESSION_TOKEN") or None,
        )
        self.table = dynamodb.Table(table_name)
        self.enabled = True
        return self

    def is_enabled(self):
        return self.enabled and self.table is not None

    def should_track_request(self, response):
        if not self.is_enabled():
            return False
        if request.method != "GET":
            return False
        if response.status_code >= 400:
            return False
        return request.endpoint in {"index", "page"}

    def record_response(self, response):
        if not self.should_track_request(response):
            return response

        cookie_name = current_app.config.get("ANALYTICS_COOKIE_NAME", "visitor_id")
        visitor_id = (request.cookies.get(cookie_name) or "").strip()
        needs_cookie = not visitor_id
        if needs_cookie:
            visitor_id = str(uuid.uuid4())

        try:
            self._record_visit(visitor_id)
        except Exception as exc:
            current_app.logger.warning("analytics tracking failed: %s", exc)
            return response

        if needs_cookie:
            response.set_cookie(
                cookie_name,
                visitor_id,
                max_age=current_app.config.get("ANALYTICS_COOKIE_MAX_AGE", 60 * 60 * 24 * 365 * 2),
                secure=not current_app.config.get("DEBUG", False),
                httponly=True,
                samesite="Lax",
            )

        return response

    def _record_visit(self, visitor_id):
        now = int(time.time())
        session_window = current_app.config.get("ANALYTICS_SESSION_WINDOW_SECONDS", 60 * 30)
        path = request.path
        user_agent = (request.headers.get("User-Agent") or "")[:250]
        ip_hash = _hash_ip(request.headers.get("X-Forwarded-For", request.remote_addr or ""))
        city = _city_from_headers()
        country_code = _country_code_from_headers()
        country_name = _country_name_from_headers() or country_code
        country_headers = _country_headers_snapshot()
        visitor_key = {"pk": f"VISITOR#{visitor_id}", "sk": "PROFILE"}
        visitor_country_key = {"pk": f"VISITOR#{visitor_id}", "sk": f"COUNTRY#{country_code}"}

        existing = self.table.get_item(Key=visitor_key, ConsistentRead=True).get("Item")
        existing_country = self.table.get_item(Key=visitor_country_key, ConsistentRead=True).get("Item")
        is_new_visitor = existing is None
        is_new_country_visitor = existing_country is None
        last_seen_at = _as_int((existing or {}).get("last_seen_at"), 0)
        is_new_session = is_new_visitor or now - last_seen_at > session_window

        if is_new_visitor:
            self.table.put_item(
                Item={
                    **visitor_key,
                    "first_seen_at": now,
                    "last_seen_at": now,
                    "last_path": path,
                    "user_agent": user_agent,
                    "ip_hash": ip_hash,
                    "country_code": country_code,
                    "country_name": country_name,
                    "total_pageviews": 1,
                    "total_sessions": 1,
                }
            )
        else:
            self.table.update_item(
                Key=visitor_key,
                UpdateExpression=(
                    "SET last_seen_at = :now, last_path = :path, user_agent = :user_agent, ip_hash = :ip_hash, "
                    "country_code = :country_code, country_name = :country_name "
                    "ADD total_pageviews :pageviews, total_sessions :sessions"
                ),
                ExpressionAttributeValues={
                    ":now": now,
                    ":path": path,
                    ":user_agent": user_agent,
                    ":ip_hash": ip_hash,
                    ":country_code": country_code,
                    ":country_name": country_name,
                    ":pageviews": 1,
                    ":sessions": 1 if is_new_session else 0,
                },
            )

        if is_new_country_visitor:
            self.table.put_item(
                Item={
                    **visitor_country_key,
                    "first_seen_at": now,
                    "last_seen_at": now,
                    "country_code": country_code,
                    "country_name": country_name,
                }
            )
        else:
            self.table.update_item(
                Key=visitor_country_key,
                UpdateExpression=(
                    "SET last_seen_at = :now, country_code = :country_code, country_name = :country_name"
                ),
                ExpressionAttributeValues={
                    ":now": now,
                    ":country_code": country_code,
                    ":country_name": country_name,
                },
            )

        self.table.update_item(
            Key={"pk": "METRICS", "sk": "TOTAL"},
            UpdateExpression=(
                "SET updated_at = :now "
                "ADD total_pageviews :pageviews, unique_visitors :visitors, total_sessions :sessions"
            ),
            ExpressionAttributeValues={
                ":now": now,
                ":pageviews": 1,
                ":visitors": 1 if is_new_visitor else 0,
                ":sessions": 1 if is_new_session else 0,
            },
        )

        self.table.update_item(
            Key={"pk": f"COUNTRY#{country_code}", "sk": "TOTAL"},
            UpdateExpression=(
                "SET country_code = :country_code, country_name = :country_name, updated_at = :now "
                "ADD total_pageviews :pageviews, unique_visitors :visitors, total_sessions :sessions"
            ),
            ExpressionAttributeValues={
                ":country_code": country_code,
                ":country_name": country_name,
                ":now": now,
                ":pageviews": 1,
                ":visitors": 1 if is_new_country_visitor else 0,
                ":sessions": 1 if is_new_session else 0,
            },
        )

        self.table.put_item(
            Item={
                "pk": "VISIT",
                "sk": f"{now:010d}#{uuid.uuid4().hex[:8]}",
                "visited_at": now,
                "visitor_hash": _hash_visitor_id(visitor_id),
                "path": path,
                "city": city or "",
                "country_code": country_code,
                "country_name": country_name,
                "is_new_visitor": is_new_visitor,
                "is_new_session": is_new_session,
                **country_headers,
            }
        )

    def _recent_visits(self, limit=5):
        items = []

        if Key is not None:
            try:
                response = self.table.query(
                    KeyConditionExpression=Key("pk").eq("VISIT"),
                    ScanIndexForward=False,
                    Limit=limit,
                )
                items = response.get("Items", [])
            except Exception:
                items = []

        if not items:
            scan_result = self.table.scan(
                FilterExpression="pk = :visit_pk",
                ExpressionAttributeValues={":visit_pk": "VISIT"},
            )
            items = scan_result.get("Items", [])
            while "LastEvaluatedKey" in scan_result:
                scan_result = self.table.scan(
                    FilterExpression="pk = :visit_pk",
                    ExpressionAttributeValues={":visit_pk": "VISIT"},
                    ExclusiveStartKey=scan_result["LastEvaluatedKey"],
                )
                items.extend(scan_result.get("Items", []))

            items.sort(key=lambda item: item.get("sk") or "", reverse=True)
            items = items[:limit]

        return [
            {
                "visited_at": _as_int(item.get("visited_at"), 0),
                "visitor_hash": item.get("visitor_hash") or "",
                "path": item.get("path") or "",
                "city": item.get("city") or "",
                "country_code": item.get("country_code") or "UNKNOWN",
                "country_name": item.get("country_name") or item.get("country_code") or "UNKNOWN",
                "is_new_visitor": bool(item.get("is_new_visitor")),
                "is_new_session": bool(item.get("is_new_session")),
                "cloudfront_city": item.get("cloudfront_city") or "",
                "cloudfront_country": item.get("cloudfront_country") or "",
                "cloudfront_country_name": item.get("cloudfront_country_name") or "",
                "cf_ip_country": item.get("cf_ip_country") or "",
                "x_city": item.get("x_city") or "",
                "x_country_code": item.get("x_country_code") or "",
                "x_country_name": item.get("x_country_name") or "",
            }
            for item in items
        ]

    def summary_data(self):
        if not self.is_enabled():
            return None

        metrics = self.table.get_item(Key={"pk": "METRICS", "sk": "TOTAL"}).get("Item") or {}
        scan_result = self.table.scan(
            FilterExpression="begins_with(pk, :country_prefix) AND sk = :total_key",
            ExpressionAttributeValues={":country_prefix": "COUNTRY#", ":total_key": "TOTAL"},
        )
        country_rows = scan_result.get("Items", [])
        while "LastEvaluatedKey" in scan_result:
            scan_result = self.table.scan(
                FilterExpression="begins_with(pk, :country_prefix) AND sk = :total_key",
                ExpressionAttributeValues={":country_prefix": "COUNTRY#", ":total_key": "TOTAL"},
                ExclusiveStartKey=scan_result["LastEvaluatedKey"],
            )
            country_rows.extend(scan_result.get("Items", []))

        countries = [
            {
                "country_code": item.get("country_code") or item.get("pk", "COUNTRY#UNKNOWN").replace("COUNTRY#", "", 1),
                "country_name": item.get("country_name") or item.get("country_code") or "UNKNOWN",
                "unique_visitors": _as_int(item.get("unique_visitors"), 0),
                "total_sessions": _as_int(item.get("total_sessions"), 0),
                "total_pageviews": _as_int(item.get("total_pageviews"), 0),
                "updated_at": _as_int(item.get("updated_at"), 0),
            }
            for item in country_rows
        ]
        countries.sort(key=lambda item: (-item["unique_visitors"], -item["total_pageviews"], item["country_code"]))

        return {
            "unique_visitors": _as_int(metrics.get("unique_visitors"), 0),
            "total_sessions": _as_int(metrics.get("total_sessions"), 0),
            "total_pageviews": _as_int(metrics.get("total_pageviews"), 0),
            "updated_at": _as_int(metrics.get("updated_at"), 0),
            "session_window_seconds": current_app.config.get("ANALYTICS_SESSION_WINDOW_SECONDS", 60 * 30),
            "countries": countries,
            "recent_visits": self._recent_visits(limit=5),
        }

    def summary_response(self):
        if not self.is_enabled():
            return jsonify({"message": "Analytics is not configured."}), 404

        token = (current_app.config.get("ANALYTICS_READ_TOKEN") or "").strip()
        if token:
            provided = (request.headers.get("X-Analytics-Token") or request.args.get("token") or "").strip()
            if provided != token:
                return jsonify({"message": "Forbidden."}), 403

        return jsonify(self.summary_data())


analytics_tracker = AnalyticsTracker()


def init_analytics(app):
    analytics_tracker.init_app(app)
    return analytics_tracker