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
        media_url = str(payload.get("url") or "")
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
    "description": "List the allowed tenant's categories and recent published posts before choosing a topic.",
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
