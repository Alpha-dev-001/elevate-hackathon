"""Mirror an externally-hosted product image (CSV row, manual entry) to
Elevate's own OSS bucket, once, permanently — so the storefront never
depends on some other host staying up. Vision-batch-sourced images already
skip this: they're uploaded to OSS at drop-time, before Qwen ever sees the
URL (see components/onboarding/ImageDropZone.tsx's uploadProductImage).

Best-effort by design, same as every other background enrichment in this
codebase (featuring, catalog audit): a mirror failure leaves the original
external URL in place rather than blocking or breaking the product.
"""
from __future__ import annotations

import logging
import time
import uuid

import httpx

from app.core.config import get_settings
from app.routers.upload import _bucket, _EXT

logger = logging.getLogger(__name__)

_FETCH_TIMEOUT = 10.0
_MAX_BYTES = 8 * 1024 * 1024  # 8MB — a product photo has no business being bigger


def _already_on_our_bucket(url: str) -> bool:
    s = get_settings()
    if not s.oss_bucket or not s.oss_region:
        return False
    return f"{s.oss_bucket}.oss-{s.oss_region}.aliyuncs.com" in url


async def mirror_image(url: str, merchant_id: str) -> str | None:
    """Fetch `url` and re-host it on our own OSS bucket. Returns the new
    public URL, or None if nothing changed (already ours, unreachable,
    not actually an image, or OSS isn't configured) — callers keep the
    original URL in every None case."""
    if not url or _already_on_our_bucket(url):
        return None

    try:
        async with httpx.AsyncClient(timeout=_FETCH_TIMEOUT, follow_redirects=True) as client:
            resp = await client.get(url)
    except (httpx.TimeoutException, httpx.TransportError) as e:
        logger.info(f"[image_mirror] fetch failed for {url}: {e}")
        return None

    if resp.status_code >= 400:
        logger.info(f"[image_mirror] {url} returned {resp.status_code}")
        return None

    content_type = resp.headers.get("content-type", "").split(";")[0].strip().lower()
    if content_type not in _EXT:
        logger.info(f"[image_mirror] {url} is not a mirrorable image type ({content_type})")
        return None

    if len(resp.content) > _MAX_BYTES:
        logger.info(f"[image_mirror] {url} exceeds {_MAX_BYTES} bytes, skipping")
        return None

    try:
        bucket, s = _bucket()
    except Exception as e:  # noqa: BLE001 — HTTPException from _bucket() when OSS isn't configured
        logger.info(f"[image_mirror] OSS not configured, skipping mirror: {e}")
        return None

    object_key = (
        f"products/{merchant_id}/mirrored_{int(time.time())}_{uuid.uuid4().hex[:8]}"
        f".{_EXT[content_type]}"
    )
    try:
        bucket.put_object(object_key, resp.content, headers={"x-oss-object-acl": "public-read"})
    except Exception as e:  # noqa: BLE001 — an OSS write failure must not break the product
        logger.warning(f"[image_mirror] OSS upload failed for {merchant_id}: {e}")
        return None

    return f"https://{s.oss_bucket}.oss-{s.oss_region}.aliyuncs.com/{object_key}"
