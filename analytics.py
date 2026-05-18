from collections import Counter
import hashlib
import time
import uuid
from urllib.parse import urlsplit

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


BOT_SIGNATURES = (
    "bot",
    "crawl",
    "crawler",
    "spider",
    "slurp",
    "wget",
    "curl",
    "python-requests",
    "python-urllib",
    "go-http-client",
    "headless",
    "phantomjs",
    "selenium",
    "scrapy",
    "httpclient",
    "claudebot",
    "gptbot",
    "perplexitybot",
    "chatgpt-user",
    "bytespider",
    "facebookexternalhit",
    "amazonbot",
    "applebot",
)


BROWSER_SIGNATURES = (
    "mozilla/",
    "chrome/",
    "safari/",
    "firefox/",
    "edg/",
    "opr/",
)


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


def _traffic_class_from_user_agent(user_agent):
    ua = (user_agent or "").strip().lower()
    if not ua:
        return "Unknown"
    if any(signature in ua for signature in BOT_SIGNATURES):
        return "Bot"
    if any(signature in ua for signature in BROWSER_SIGNATURES):
        return "Browser"
    return "Unknown"


def _referer_host(referer):
    return urlsplit(referer or "").netloc.lower().strip()


def _source_from_referer(referer):
    host = _referer_host(referer)
    if not host:
        return "Direct"

    app_host = urlsplit(current_app.config.get("APP_BASE_URL", "")).netloc.lower().strip()
    if app_host and (host == app_host or host.endswith(f".{app_host}")):
        return "Internal"
    if "google." in host:
        return "Google"
    if "linkedin.com" in host:
        return "LinkedIn"
    if "github.com" in host:
        return "GitHub"
    if "bing.com" in host:
        return "Bing"
    if "scholar.google" in host:
        return "Google Scholar"
    if "chatgpt.com" in host or "openai.com" in host:
        return "ChatGPT"
    if "claude.ai" in host or "anthropic.com" in host:
        return "Claude"
    if "perplexity.ai" in host:
        return "Perplexity"
    if "facebook.com" in host or "m.facebook.com" in host:
        return "Facebook"
    if "instagram.com" in host:
        return "Instagram"
    if "x.com" in host or "twitter.com" in host:
        return "X"
    return host


def _share_percent(numerator, denominator):
    if not denominator:
        return 0
    return round((numerator / denominator) * 100, 1)


def _group_small_countries(countries, minimum_visitors=5):
    primary_countries = []
    other_countries = []

    for country in countries:
        if country.get("unique_visitors", 0) < minimum_visitors:
            other_countries.append(country)
        else:
            primary_countries.append(country)

    if not other_countries:
        return primary_countries

    primary_countries.append(
        {
            "country_code": "OTHERS",
            "country_name": "Others",
            "unique_visitors": sum(item.get("unique_visitors", 0) for item in other_countries),
            "total_sessions": sum(item.get("total_sessions", 0) for item in other_countries),
            "total_pageviews": sum(item.get("total_pageviews", 0) for item in other_countries),
            "updated_at": max((item.get("updated_at", 0) for item in other_countries), default=0),
        }
    )

    return primary_countries


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
        referer = (request.headers.get("Referer") or "")[:400]
        ip_hash = _hash_ip(request.headers.get("X-Forwarded-For", request.remote_addr or ""))
        city = _city_from_headers()
        country_code = _country_code_from_headers()
        country_name = _country_name_from_headers() or country_code
        country_headers = _country_headers_snapshot()
        traffic_class = _traffic_class_from_user_agent(user_agent)
        source = _source_from_referer(referer)
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
                "referer_host": _referer_host(referer),
                "source": source,
                "traffic_class": traffic_class,
                "country_code": country_code,
                "country_name": country_name,
                "is_new_visitor": is_new_visitor,
                "is_new_session": is_new_session,
                **country_headers,
            }
        )

    def _visit_items(self, limit=None):
        items = []

        if Key is not None:
            try:
                query_kwargs = {
                    "KeyConditionExpression": Key("pk").eq("VISIT"),
                    "ScanIndexForward": False,
                }
                if limit is not None:
                    query_kwargs["Limit"] = limit

                response = self.table.query(**query_kwargs)
                items.extend(response.get("Items", []))
                while "LastEvaluatedKey" in response and (limit is None or len(items) < limit):
                    query_kwargs["ExclusiveStartKey"] = response["LastEvaluatedKey"]
                    if limit is not None:
                        query_kwargs["Limit"] = limit - len(items)
                    response = self.table.query(**query_kwargs)
                    items.extend(response.get("Items", []))
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
            if limit is not None:
                items = items[:limit]

        return items

    def _visit_record(self, item):
        return {
            "visited_at": _as_int(item.get("visited_at"), 0),
            "visitor_hash": item.get("visitor_hash") or "",
            "path": item.get("path") or "",
            "city": item.get("city") or "",
            "source": item.get("source") or "Direct",
            "referer_host": item.get("referer_host") or "",
            "traffic_class": item.get("traffic_class") or "Unknown",
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

    def _recent_visits(self, limit=5):
        items = self._visit_items(limit=limit)

        return [self._visit_record(item) for item in items]

    def _aggregate_visit_summaries(self, visits):
        source_counts = Counter()
        path_counts = Counter()
        traffic_counts = Counter()
        browser_hashes = set()
        bot_hashes = set()

        for visit in visits:
            source_counts[visit["source"] or "Direct"] += 1
            path_counts[visit["path"] or "/"] += 1
            traffic_counts[visit["traffic_class"] or "Unknown"] += 1

            visitor_hash = visit.get("visitor_hash") or ""
            if visit["traffic_class"] == "Browser" and visitor_hash:
                browser_hashes.add(visitor_hash)
            if visit["traffic_class"] == "Bot" and visitor_hash:
                bot_hashes.add(visitor_hash)

        total_visits = len(visits)
        top_sources = [
            {
                "label": label,
                "count": count,
                "share_percent": _share_percent(count, total_visits),
            }
            for label, count in source_counts.most_common(5)
        ]
        top_paths = [
            {
                "label": label,
                "count": count,
                "share_percent": _share_percent(count, total_visits),
            }
            for label, count in path_counts.most_common(5)
        ]

        return {
            "raw_tracked_visits": total_visits,
            "estimated_human_visitors": len(browser_hashes),
            "bot_visitors": len(bot_hashes),
            "browser_visits": traffic_counts.get("Browser", 0),
            "bot_visits": traffic_counts.get("Bot", 0),
            "unknown_visits": traffic_counts.get("Unknown", 0),
            "top_sources": top_sources,
            "top_paths": top_paths,
        }

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
        countries = _group_small_countries(countries, minimum_visitors=5)
        countries.sort(
            key=lambda item: (
                item["country_code"] == "OTHERS",
                -item["unique_visitors"],
                -item["total_pageviews"],
                item["country_code"],
            )
        )
        visits = self._recent_visits(limit=5000)
        visit_summary = self._aggregate_visit_summaries(visits)

        return {
            "unique_visitors": _as_int(metrics.get("unique_visitors"), 0),
            "total_sessions": _as_int(metrics.get("total_sessions"), 0),
            "total_pageviews": _as_int(metrics.get("total_pageviews"), 0),
            "updated_at": _as_int(metrics.get("updated_at"), 0),
            "session_window_seconds": current_app.config.get("ANALYTICS_SESSION_WINDOW_SECONDS", 60 * 30),
            "countries": countries,
            "recent_visits": visits[:5],
            "recent_sample_size": 5,
            **visit_summary,
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