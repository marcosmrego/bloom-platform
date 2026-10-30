"""Restricted Hermes tools for the Bloom editorial API."""

from __future__ import annotations

import hashlib
import os
import re
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import requests

from tools.registry import tool_error, tool_result


ALLOWED_TENANTS = {"viralbarato", "mundonoprato"}
TIMEOUT = (10, 60)


def _config() -> tuple[str, str]:
    base_url = os.getenv("BLOOM_API_URL", "").strip().rstrip("/")
    token = os.getenv("BLOOM_CONTENT_API_TOKEN", "").strip()
    parsed = urlparse(base_url)
    if parsed.scheme != "https" or not parsed.netloc or parsed.path:
        raise ValueError("BLOOM_API_URL must be an HTTPS origin without a path")
    if not token:
        raise ValueError("BLOOM_CONTENT_API_TOKEN is not configured")
    return base_url, token


def _tenant(value: Any) -> str:
    tenant = str(value or "").strip().lower()
    if tenant not in ALLOWED_TENANTS:
        raise ValueError("tenant must be viralbarato or mundonoprato")
    return tenant


def _headers() -> dict[str, str]:
    _base_url, token = _config()
    return {"Authorization": f"Bearer {token}"}


def _json_response(response: requests.Response) -> dict[str, Any]:
    try:
        payload = response.json()
    except ValueError:
        payload = {"detail": "Bloom returned a non-JSON response"}
    if response.status_code >= 400:
        detail = payload.get("detail") if isinstance(payload, dict) else None
        raise RuntimeError(f"Bloom API returned HTTP {response.status_code}: {detail}")
    if not isinstance(payload, dict):
        raise RuntimeError("Bloom API returned an unexpected response")
    return payload


def _available() -> bool:
    try:
        _config()
        return True
    except ValueError:
        return False


def _handle_context(args: dict, **_kwargs) -> str:
    try:
        tenant = _tenant(args.get("tenant"))
        base_url, _token = _config()
        categories = requests.get(
            f"{base_url}/api/v1/{tenant}/categories",
            timeout=TIMEOUT,
        )
        posts = requests.get(
            f"{base_url}/api/v1/{tenant}/posts",
            params={"page": 1, "page_size": 50},
            timeout=TIMEOUT,
        )
        seasonal = requests.get(
            f"{base_url}/api/v1/{tenant}/editorial/seasonal-opportunities",
            headers=_headers(),
            timeout=TIMEOUT,
        )
        return tool_result(
            {
                "success": True,
                "tenant": tenant,
                "categories": _json_response(categories).get("items", []),
                "recent_posts": [
                    {
                        key: item.get(key)
                        for key in ("id", "title", "slug", "category_slug", "published_at")
                    }
                    for item in _json_response(posts).get("items", [])
                ],
                "seasonal_opportunities": _json_response(seasonal).get("items", []),
            }
        )
    except Exception as exc:
        return tool_error(f"Bloom context failed: {exc}")


def _handle_upload_media(args: dict, **_kwargs) -> str:
    try:
        tenant = _tenant(args.get("tenant"))
        raw_path = str(args.get("path") or "").strip()
        path = Path(raw_path).expanduser().resolve()
        hermes_home = Path(os.getenv("HERMES_HOME", "~/.hermes")).expanduser().resolve()
        allowed_root = (hermes_home / "cache" / "images").resolve()
        if allowed_root not in path.parents:
            raise ValueError("image must be inside the Hermes image cache")
        if path.suffix.lower() not in {".png", ".jpg", ".jpeg", ".webp"}:
            raise ValueError("image must be PNG, JPEG or WebP")
        content = path.read_bytes()
        content_type = {
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".webp": "image/webp",
        }[path.suffix.lower()]

        base_url, _token = _config()
        response = requests.post(
            f"{base_url}/api/v1/{tenant}/media",
            headers=_headers(),
            files={"image": (path.name, content, content_type)},
            timeout=TIMEOUT,
        )
        payload = _json_response(response)
        media_url = str(payload.get("image_url") or "")
        if not media_url.startswith(f"/media/{tenant}/") or not media_url.endswith(".webp"):
            raise RuntimeError("Bloom returned an invalid media URL")
        verification = requests.get(
            f"{base_url}{media_url}",
            headers=_headers(),
            timeout=TIMEOUT,
        )
        if (
            verification.status_code != 200
            or verification.headers.get("content-type", "").split(";", 1)[0]
            != "image/webp"
        ):
            raise RuntimeError("Persisted Bloom media did not return HTTP 200 WebP")
        payload["success"] = True
        payload["http_verified"] = True
        return tool_result(payload)
    except Exception as exc:
        return tool_error(f"Bloom media upload failed: {exc}")


def _handle_check_topic(args: dict, **_kwargs) -> str:
    try:
        tenant = _tenant(args.get("tenant"))
        topic = str(args.get("topic") or "").strip()
        if len(topic) < 10 or len(topic) > 200:
            raise ValueError("topic must contain 10-200 characters")
        base_url, _token = _config()
        response = requests.post(
            f"{base_url}/api/v1/{tenant}/editorial/similarity",
            headers=_headers(),
            json={"topic": topic},
            timeout=TIMEOUT,
        )
        payload = _json_response(response)
        payload["success"] = True
        return tool_result(payload)
    except Exception as exc:
        return tool_error(f"Bloom topic similarity check failed: {exc}")


def _handle_monetization_backlog(args: dict, **_kwargs) -> str:
    try:
        tenant = _tenant(args.get("tenant"))
        limit = int(args.get("limit") or 10)
        if limit < 1 or limit > 20:
            raise ValueError("limit must be between 1 and 20")
        base_url, _token = _config()
        response = requests.get(
            f"{base_url}/api/v1/{tenant}/editorial/monetization/backlog",
            headers=_headers(), params={"limit": limit}, timeout=TIMEOUT,
        )
        payload = _json_response(response)
        payload["success"] = True
        return tool_result(payload)
    except Exception as exc:
        return tool_error(f"Bloom monetization backlog failed: {exc}")


def _handle_build_affiliate_search(args: dict, **_kwargs) -> str:
    try:
        tenant = _tenant(args.get("tenant"))
        query = str(args.get("query") or "").strip()
        if len(query) < 3 or len(query) > 120:
            raise ValueError("query must contain 3-120 characters")
        base_url, _token = _config()
        response = requests.post(
            f"{base_url}/api/v1/{tenant}/editorial/monetization/search-destination",
            headers=_headers(), json={"query": query}, timeout=TIMEOUT,
        )
        payload = _json_response(response)
        payload["success"] = True
        return tool_result(payload)
    except Exception as exc:
        return tool_error(f"Bloom affiliate search build failed: {exc}")


def _handle_propose_monetization(args: dict, **_kwargs) -> str:
    try:
        tenant = _tenant(args.get("tenant"))
        key = str(args.get("idempotency_key") or "").strip()
        if len(key) < 8:
            raise ValueError("idempotency_key is required")
        proposal = dict(args.get("proposal") or {})
        if proposal.get("link_type") not in {"product", "search", "no_match"}:
            raise ValueError("link_type must be product, search or no_match")
        base_url, _token = _config()
        headers = _headers()
        headers["Idempotency-Key"] = key
        response = requests.post(
            f"{base_url}/api/v1/{tenant}/editorial/monetization/proposals",
            headers=headers, json=proposal, timeout=TIMEOUT,
        )
        payload = _json_response(response)
        payload["success"] = True
        return tool_result(payload)
    except Exception as exc:
        return tool_error(f"Bloom monetization proposal failed: {exc}")


def _handle_editorial_review_backlog(args: dict, **_kwargs) -> str:
    try:
        tenant = _tenant(args.get("tenant"))
        limit = int(args.get("limit") or 1)
        if limit < 1 or limit > 3:
            raise ValueError("limit must be between 1 and 3")
        base_url, _token = _config()
        response = requests.get(
            f"{base_url}/api/v1/{tenant}/editorial/reviewer/backlog",
            headers=_headers(), params={"limit": limit}, timeout=TIMEOUT,
        )
        payload = _json_response(response)
        payload["success"] = True
        return tool_result(payload)
    except Exception as exc:
        return tool_error(f"Bloom editorial review backlog failed: {exc}")


def _handle_performance_metrics(args: dict, **_kwargs) -> str:
    try:
        tenant_value = args.get("tenant")
        tenant = _tenant(tenant_value) if tenant_value else None
        days = int(args.get("days") or 7)
        if days not in {7, 30, 90}:
            raise ValueError("days must be 7, 30 or 90")
        base_url, _token = _config()
        params: dict[str, Any] = {"days": days}
        if tenant:
            params["tenant_slug"] = tenant
        response = requests.get(
            f"{base_url}/api/v1/editorial/review/metrics",
            headers=_headers(), params=params, timeout=TIMEOUT,
        )
        payload = _json_response(response)
        payload["success"] = True
        return tool_result(payload)
    except Exception as exc:
        return tool_error(f"Bloom performance metrics failed: {exc}")


def _handle_traffic_recovery_backlog(args: dict, **_kwargs) -> str:
    try:
        limit = int(args.get("limit") or 5)
        if limit < 1 or limit > 20:
            raise ValueError("limit must be between 1 and 20")
        base_url, _token = _config()
        response = requests.get(
            f"{base_url}/api/v1/editorial/traffic-recovery/backlog",
            headers=_headers(), params={"limit": limit}, timeout=TIMEOUT,
        )
        payload = _json_response(response)
        payload["success"] = True
        return tool_result(payload)
    except Exception as exc:
        return tool_error(f"Bloom traffic recovery backlog failed: {exc}")


def _handle_submit_traffic_recovery(args: dict, **_kwargs) -> str:
    try:
        tenant = _tenant(args.get("tenant"))
        key = str(args.get("idempotency_key") or "").strip()
        if len(key) < 8:
            raise ValueError("idempotency_key is required")
        attempt = dict(args.get("attempt") or {})
        base_url, _token = _config()
        headers = _headers()
        headers["Idempotency-Key"] = key
        response = requests.post(
            f"{base_url}/api/v1/{tenant}/editorial/traffic-recovery/attempts",
            headers=headers, json=attempt, timeout=TIMEOUT,
        )
        payload = _json_response(response)
        payload["success"] = True
        return tool_result(payload)
    except Exception as exc:
        return tool_error(f"Bloom traffic recovery submission failed: {exc}")


def _handle_submit_editorial_review(args: dict, **_kwargs) -> str:
    try:
        tenant = _tenant(args.get("tenant"))
        key = str(args.get("idempotency_key") or "").strip()
        if len(key) < 8:
            raise ValueError("idempotency_key is required")
        report = dict(args.get("report") or {})
        if report.get("recommendation") not in {"pass", "needs_changes", "block"}:
            raise ValueError("recommendation must be pass, needs_changes or block")
        base_url, _token = _config()
        headers = _headers()
        headers["Idempotency-Key"] = key
        response = requests.post(
            f"{base_url}/api/v1/{tenant}/editorial/reviewer/reports",
            headers=headers, json=report, timeout=TIMEOUT,
        )
        payload = _json_response(response)
        payload["success"] = True
        return tool_result(payload)
    except Exception as exc:
        return tool_error(f"Bloom editorial review submission failed: {exc}")


def _handle_register_product(args: dict, **_kwargs) -> str:
    try:
        tenant = _tenant(args.get("tenant"))
        if tenant != "viralbarato":
            raise ValueError("Mercado Livre products are enabled only for viralbarato")
        name = str(args.get("name") or "").strip()
        if name and not 3 <= len(name) <= 200:
            raise ValueError("name must contain 3-200 characters")
        affiliate_link = str(args.get("affiliate_link") or "").strip()
        if urlparse(affiliate_link).scheme != "https":
            raise ValueError("affiliate_link must be an HTTPS URL")
        body: dict[str, Any] = {"affiliate_link": affiliate_link}
        if name:
            body["name"] = name
        item_id = str(args.get("item_id") or "").strip()
        if item_id:
            body["item_id"] = item_id
        base_url, _token = _config()
        response = requests.post(
            f"{base_url}/api/v1/{tenant}/editorial/products/mercadolivre",
            headers=_headers(), json=body, timeout=TIMEOUT,
        )
        payload = _json_response(response)
        payload["success"] = True
        return tool_result(payload)
    except Exception as exc:
        return tool_error(f"Bloom product registration failed: {exc}")


def _handle_claim_draft_request(args: dict, **_kwargs) -> str:
    try:
        tenant = _tenant(args.get("tenant"))
        if tenant != "viralbarato":
            raise ValueError("Draft requests are enabled only for viralbarato")
        base_url, _token = _config()
        response = requests.post(
            f"{base_url}/api/v1/{tenant}/editorial/draft-requests/claim",
            headers=_headers(), timeout=TIMEOUT,
        )
        payload = _json_response(response)
        payload["success"] = True
        return tool_result(payload)
    except Exception as exc:
        return tool_error(f"Bloom draft request claim failed: {exc}")


def _handle_finish_draft_request(args: dict, **_kwargs) -> str:
    try:
        tenant = _tenant(args.get("tenant"))
        if tenant != "viralbarato":
            raise ValueError("Draft requests are enabled only for viralbarato")
        request_id = int(args.get("request_id"))
        status = str(args.get("status") or "").strip()
        if status not in {"completed", "failed"}:
            raise ValueError("status must be completed or failed")
        body: dict[str, Any] = {"status": status}
        if status == "completed":
            body["post_id"] = int(args.get("post_id"))
        else:
            error = str(args.get("error") or "").strip()
            if not error:
                raise ValueError("error is required when status is failed")
            body["error"] = error[:500]
        base_url, _token = _config()
        response = requests.post(
            f"{base_url}/api/v1/{tenant}/editorial/draft-requests/{request_id}/result",
            headers=_headers(), json=body, timeout=TIMEOUT,
        )
        payload = _json_response(response)
        payload["success"] = True
        return tool_result(payload)
    except Exception as exc:
        return tool_error(f"Bloom draft request result failed: {exc}")


def _handle_create_draft(args: dict, **_kwargs) -> str:
    try:
        tenant = _tenant(args.get("tenant"))
        idempotency_key = str(args.get("idempotency_key") or "").strip()
        if len(idempotency_key) < 8:
            raise ValueError("idempotency_key is required")

        payload = dict(args.get("post") or {})
        payload["tenant_slug"] = tenant
        payload["status"] = "draft"
        payload["created_by"] = "hermes-bloom"
        image_url = str(payload.get("image_url") or "")
        if image_url and not image_url.startswith(f"/media/{tenant}/"):
            raise ValueError("image_url must refer to uploaded Bloom media")
        if not str(payload.get("title") or "").strip():
            raise ValueError("post.title is required")
        if not str(payload.get("content") or "").strip():
            raise ValueError("post.content is required")
        if len(str(payload.get("content") or "").strip()) < 1000:
            raise ValueError("post.content must contain at least 1000 characters")
        if len(re.findall(r"(?m)^##\s+\S", str(payload.get("content") or ""))) < 2:
            raise ValueError("post.content must contain at least two H2 sections")
        sources = payload.get("sources")
        if not isinstance(sources, list) or len(sources) < 2:
            raise ValueError("post.sources must contain at least two extracted sources")
        unique_urls = set()
        for source in sources:
            if not isinstance(source, dict):
                raise ValueError("each source must be an object")
            source_url = str(source.get("url") or "").strip()
            parsed_source = urlparse(source_url)
            if parsed_source.scheme not in {"http", "https"} or not parsed_source.netloc:
                raise ValueError("each source must have a valid HTTP(S) URL")
            unique_urls.add(source_url.rstrip("/"))
            evidence = source.get("evidence")
            if not isinstance(evidence, list) or not any(
                str(item).strip() for item in evidence
            ):
                raise ValueError("each source must include extracted evidence")
        if len(unique_urls) < 2:
            raise ValueError("post.sources must contain two unique URLs")

        base_url, _token = _config()
        headers = _headers()
        headers["Idempotency-Key"] = idempotency_key
        response = requests.post(
            f"{base_url}/api/v1/{tenant}/posts",
            headers=headers,
            json=payload,
            timeout=TIMEOUT,
        )
        result = _json_response(response)
        result["success"] = True
        request_body = response.request.body or b""
        if isinstance(request_body, str):
            request_body = request_body.encode("utf-8")
        result["request_sha256"] = hashlib.sha256(request_body).hexdigest()
        return tool_result(result)
    except Exception as exc:
        return tool_error(f"Bloom draft creation failed: {exc}")


BLOOM_CONTEXT_SCHEMA = {
    "name": "bloom_context",
    "description": "List categories, recent posts and active seasonal opportunities before choosing a topic.",
    "parameters": {
        "type": "object",
        "properties": {
            "tenant": {
                "type": "string",
                "enum": sorted(ALLOWED_TENANTS),
            }
        },
        "required": ["tenant"],
    },
}

BLOOM_UPLOAD_MEDIA_SCHEMA = {
    "name": "bloom_upload_media",
    "description": "Upload a generated image from the Hermes cache. Bloom validates and converts it to WebP.",
    "parameters": {
        "type": "object",
        "properties": {
            "tenant": {"type": "string", "enum": sorted(ALLOWED_TENANTS)},
            "path": {"type": "string"},
        },
        "required": ["tenant", "path"],
    },
}

BLOOM_CHECK_TOPIC_SCHEMA = {
    "name": "bloom_check_topic",
    "description": "Check a proposed topic against existing Bloom drafts and posts before research and generation.",
    "parameters": {
        "type": "object",
        "properties": {
            "tenant": {"type": "string", "enum": sorted(ALLOWED_TENANTS)},
            "topic": {"type": "string", "minLength": 10, "maxLength": 200},
        },
        "required": ["tenant", "topic"],
    },
}

BLOOM_MONETIZATION_BACKLOG_SCHEMA = {
    "name": "bloom_monetization_backlog",
    "description": "List published posts without an affiliate destination, ordered by measured traffic.",
    "parameters": {
        "type": "object",
        "properties": {
            "tenant": {"type": "string", "enum": sorted(ALLOWED_TENANTS)},
            "limit": {"type": "integer", "minimum": 1, "maximum": 20},
        },
        "required": ["tenant"],
    },
}

BLOOM_BUILD_AFFILIATE_SEARCH_SCHEMA = {
    "name": "bloom_build_affiliate_search",
    "description": "Build a canonical Amazon Brazil affiliate search URL from plain, article-aligned product terms.",
    "parameters": {
        "type": "object",
        "properties": {
            "tenant": {"type": "string", "enum": sorted(ALLOWED_TENANTS)},
            "query": {"type": "string", "minLength": 3, "maxLength": 120},
        },
        "required": ["tenant", "query"],
    },
}

BLOOM_PROPOSE_MONETIZATION_SCHEMA = {
    "name": "bloom_propose_monetization",
    "description": "Submit a monetization proposal for human review. This tool can never alter a published post.",
    "parameters": {
        "type": "object",
        "properties": {
            "tenant": {"type": "string", "enum": sorted(ALLOWED_TENANTS)},
            "idempotency_key": {"type": "string", "minLength": 8, "maxLength": 128},
            "proposal": {
                "type": "object",
                "properties": {
                    "post_id": {"type": "integer", "minimum": 1},
                    "link_type": {"type": "string", "enum": ["product", "search", "no_match"]},
                    "product_asin": {"type": "string"},
                    "product_title": {"type": "string"},
                    "destination_url": {"type": "string"},
                    "rationale": {"type": "string", "minLength": 20, "maxLength": 2000},
                    "evidence": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "url": {"type": "string", "format": "uri"},
                                "title": {"type": "string"},
                                "extracted_at": {"type": "string"},
                                "evidence": {"type": "array", "items": {"type": "string"}},
                                "source_type": {"type": "string", "enum": ["official", "primary", "secondary"]},
                            },
                            "required": ["url", "title", "extracted_at", "evidence", "source_type"],
                        },
                    },
                },
                "required": ["post_id", "link_type", "rationale", "evidence"],
            },
        },
        "required": ["tenant", "idempotency_key", "proposal"],
    },
}

BLOOM_EDITORIAL_REVIEW_BACKLOG_SCHEMA = {
    "name": "bloom_editorial_review_backlog",
    "description": "List draft posts that need a first-pass agent review. This tool is read-only.",
    "parameters": {
        "type": "object",
        "properties": {
            "tenant": {"type": "string", "enum": sorted(ALLOWED_TENANTS)},
            "limit": {"type": "integer", "minimum": 1, "maximum": 3},
        },
        "required": ["tenant"],
    },
}

BLOOM_PERFORMANCE_METRICS_SCHEMA = {
    "name": "bloom_performance_metrics",
    "description": "Read Bloom traffic, CTR, finance status and actionable alerts. This tool is read-only.",
    "parameters": {
        "type": "object",
        "properties": {
            "tenant": {"type": "string", "enum": sorted(ALLOWED_TENANTS)},
            "days": {"type": "integer", "enum": [7, 30, 90]},
        },
    },
}


BLOOM_TRAFFIC_RECOVERY_BACKLOG_SCHEMA = {
    "name": "bloom_traffic_recovery_backlog",
    "description": "List a bounded, cooldown-aware queue of published posts eligible for traffic recovery.",
    "parameters": {
        "type": "object",
        "properties": {"limit": {"type": "integer", "minimum": 1, "maximum": 20}},
    },
}


BLOOM_SUBMIT_TRAFFIC_RECOVERY_SCHEMA = {
    "name": "bloom_submit_traffic_recovery",
    "description": "Record one evidenced low-risk recovery action. It cannot edit or unpublish content.",
    "parameters": {
        "type": "object",
        "properties": {
            "tenant": {"type": "string", "enum": sorted(ALLOWED_TENANTS)},
            "idempotency_key": {"type": "string", "minLength": 8, "maxLength": 128},
            "attempt": {
                "type": "object",
                "properties": {
                    "post_id": {"type": "integer", "minimum": 1},
                    "diagnosis": {"type": "string", "enum": ["indexing_unknown", "not_indexed", "low_impressions", "low_ctr", "missing_internal_links", "distribution_gap", "low_demand"]},
                    "action": {"type": "string", "enum": ["request_indexing", "generate_social_package", "propose_internal_links", "propose_metadata", "monitor", "escalate_human"]},
                    "rationale": {"type": "string", "minLength": 20, "maxLength": 2000},
                    "evidence": {"type": "array", "maxItems": 20, "items": {"type": "object"}},
                    "status": {"type": "string", "enum": ["completed", "blocked", "ineffective"]},
                },
                "required": ["post_id", "diagnosis", "action", "rationale", "evidence", "status"],
            },
        },
        "required": ["tenant", "idempotency_key", "attempt"],
    },
}


BLOOM_SUBMIT_EDITORIAL_REVIEW_SCHEMA = {
    "name": "bloom_submit_editorial_review",
    "description": "Submit a structured first-pass review for a Bloom draft. It cannot edit, approve, reject or publish.",
    "parameters": {
        "type": "object",
        "properties": {
            "tenant": {"type": "string", "enum": sorted(ALLOWED_TENANTS)},
            "idempotency_key": {"type": "string", "minLength": 8, "maxLength": 128},
            "report": {
                "type": "object",
                "properties": {
                    "post_id": {"type": "integer", "minimum": 1},
                    "input_hash": {"type": "string", "pattern": "^[a-f0-9]{64}$"},
                    "recommendation": {"type": "string", "enum": ["pass", "needs_changes", "block"]},
                    "risk_level": {"type": "string", "enum": ["low", "medium", "high"]},
                    "summary": {"type": "string", "minLength": 20, "maxLength": 2000},
                    "checks": {
                        "type": "array", "minItems": 6, "maxItems": 30,
                        "items": {
                            "type": "object",
                            "properties": {
                                "code": {"type": "string", "pattern": "^[a-z][a-z0-9_]*$"},
                                "status": {"type": "string", "enum": ["pass", "warn", "fail"]},
                                "severity": {"type": "string", "enum": ["low", "medium", "high"]},
                                "evidence": {"type": "string", "minLength": 3, "maxLength": 1000},
                                "recommendation": {"type": "string", "maxLength": 1000},
                            },
                            "required": ["code", "status", "severity", "evidence"],
                        },
                    },
                    "suggested_edits": {
                        "type": "array", "maxItems": 20,
                        "items": {"type": "string", "minLength": 1, "maxLength": 1000},
                    },
                },
                "required": ["post_id", "input_hash", "recommendation", "risk_level", "summary", "checks"],
            },
        },
        "required": ["tenant", "idempotency_key", "report"],
    },
}


BLOOM_REGISTER_PRODUCT_SCHEMA = {
    "name": "bloom_register_product",
    "description": (
        "Register a Mercado Livre affiliate product for ViralBarato from its affiliate "
        "link (the name is optional and, when given, is checked against the link). Bloom verifies the item behind the link and returns the "
        "external_id to use as post.product_external_id. It never publishes."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "tenant": {"type": "string", "enum": ["viralbarato"]},
            "name": {"type": "string", "minLength": 3, "maxLength": 200},
            "affiliate_link": {"type": "string", "format": "uri"},
            "item_id": {
                "type": "string",
                "description": "Optional MLB item id, only when the link does not reveal the item.",
            },
        },
        "required": ["tenant", "affiliate_link"],
    },
}


BLOOM_CLAIM_DRAFT_REQUEST_SCHEMA = {
    "name": "bloom_claim_draft_request",
    "description": (
        "Take the oldest pending product draft request queued in the Bloom panel. "
        "Returns request=null when the queue is empty. The product is already registered "
        "and verified: use its external_id as post.product_external_id."
    ),
    "parameters": {
        "type": "object",
        "properties": {"tenant": {"type": "string", "enum": ["viralbarato"]}},
        "required": ["tenant"],
    },
}


BLOOM_FINISH_DRAFT_REQUEST_SCHEMA = {
    "name": "bloom_finish_draft_request",
    "description": (
        "Report the outcome of a claimed draft request: completed with the draft post_id, "
        "or failed with a short reason the editor can read in the panel."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "tenant": {"type": "string", "enum": ["viralbarato"]},
            "request_id": {"type": "integer"},
            "status": {"type": "string", "enum": ["completed", "failed"]},
            "post_id": {"type": "integer"},
            "error": {"type": "string", "maxLength": 500},
        },
        "required": ["tenant", "request_id", "status"],
    },
}


BLOOM_CREATE_DRAFT_SCHEMA = {
    "name": "bloom_create_draft",
    "description": "Create an idempotent Bloom draft. This tool can never publish.",
    "parameters": {
        "type": "object",
        "properties": {
            "tenant": {"type": "string", "enum": sorted(ALLOWED_TENANTS)},
            "idempotency_key": {"type": "string", "minLength": 8, "maxLength": 128},
            "post": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "slug": {"type": "string"},
                    "excerpt": {"type": "string"},
                    "content": {"type": "string"},
                    "image_url": {"type": "string"},
                    "category_slug": {"type": "string"},
                    "product_asin": {"type": "string"},
                    "product_external_id": {"type": "string"},
                    "rating": {"type": "number", "minimum": 0, "maximum": 5},
                    "pros": {"type": "array", "items": {"type": "string"}},
                    "cons": {"type": "array", "items": {"type": "string"}},
                    "tags": {"type": "array", "items": {"type": "string"}},
                    "seo_title": {"type": "string"},
                    "seo_description": {"type": "string"},
                    "sources": {
                        "type": "array",
                        "minItems": 2,
                        "items": {
                            "type": "object",
                            "properties": {
                                "url": {"type": "string", "format": "uri"},
                                "title": {"type": "string", "minLength": 1},
                                "extracted_at": {"type": "string", "minLength": 1},
                                "evidence": {
                                    "type": "array",
                                    "minItems": 1,
                                    "items": {"type": "string", "minLength": 1},
                                },
                                "source_type": {
                                    "type": "string",
                                    "enum": ["official", "primary", "secondary"],
                                },
                            },
                            "required": [
                                "url",
                                "title",
                                "extracted_at",
                                "evidence",
                                "source_type",
                            ],
                        },
                    },
                },
                "required": [
                    "title",
                    "excerpt",
                    "content",
                    "image_url",
                    "category_slug",
                    "tags",
                    "seo_title",
                    "seo_description",
                    "sources",
                ],
            },
        },
        "required": ["tenant", "idempotency_key", "post"],
    },
}


def register(ctx) -> None:
    for name, schema, handler in (
        ("bloom_context", BLOOM_CONTEXT_SCHEMA, _handle_context),
        ("bloom_check_topic", BLOOM_CHECK_TOPIC_SCHEMA, _handle_check_topic),
        ("bloom_monetization_backlog", BLOOM_MONETIZATION_BACKLOG_SCHEMA, _handle_monetization_backlog),
        ("bloom_build_affiliate_search", BLOOM_BUILD_AFFILIATE_SEARCH_SCHEMA, _handle_build_affiliate_search),
        ("bloom_propose_monetization", BLOOM_PROPOSE_MONETIZATION_SCHEMA, _handle_propose_monetization),
        ("bloom_editorial_review_backlog", BLOOM_EDITORIAL_REVIEW_BACKLOG_SCHEMA, _handle_editorial_review_backlog),
        ("bloom_performance_metrics", BLOOM_PERFORMANCE_METRICS_SCHEMA, _handle_performance_metrics),
        ("bloom_traffic_recovery_backlog", BLOOM_TRAFFIC_RECOVERY_BACKLOG_SCHEMA, _handle_traffic_recovery_backlog),
        ("bloom_submit_traffic_recovery", BLOOM_SUBMIT_TRAFFIC_RECOVERY_SCHEMA, _handle_submit_traffic_recovery),
        ("bloom_submit_editorial_review", BLOOM_SUBMIT_EDITORIAL_REVIEW_SCHEMA, _handle_submit_editorial_review),
        ("bloom_register_product", BLOOM_REGISTER_PRODUCT_SCHEMA, _handle_register_product),
        ("bloom_claim_draft_request", BLOOM_CLAIM_DRAFT_REQUEST_SCHEMA, _handle_claim_draft_request),
        ("bloom_finish_draft_request", BLOOM_FINISH_DRAFT_REQUEST_SCHEMA, _handle_finish_draft_request),
        ("bloom_upload_media", BLOOM_UPLOAD_MEDIA_SCHEMA, _handle_upload_media),
        ("bloom_create_draft", BLOOM_CREATE_DRAFT_SCHEMA, _handle_create_draft),
    ):
        ctx.register_tool(
            name=name,
            toolset="bloom_content",
            schema=schema,
            handler=handler,
            check_fn=_available,
            emoji="🌸",
        )
