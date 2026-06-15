"""
Direct-to-OSS logo upload via presigned PUT URLs.

FastAPI never handles the file bytes — it signs a one-shot, 15-minute PUT URL
scoped to a single object key, and the browser uploads straight to OSS. The
signed URL forces `x-oss-object-acl: public-read` so the uploaded object is
publicly readable (qwen-vl can fetch it, the storefront can serve it) while the
bucket itself stays private.
"""
import time
import uuid
import logging

import oss2
from fastapi import APIRouter, Depends, HTTPException

from app.core.config import get_settings
from app.core.security import get_current_merchant
from app.models.db_models import MerchantDB
from app.models.schemas import PresignedUploadRequest, PresignedUploadResponse

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/upload", tags=["upload"])

# content-type -> extension for the object key
_EXT = {
    "image/png": "png",
    "image/jpeg": "jpg",
    "image/jpg": "jpg",
    "image/webp": "webp",
    "image/gif": "gif",
    "image/svg+xml": "svg",
}

_UPLOAD_TTL = 900  # 15 minutes


def _bucket():
    """Build an OSS bucket client (V4 signing). 503 if OSS isn't configured."""
    s = get_settings()
    if not (s.oss_access_key_id and s.oss_access_key_secret and s.oss_bucket and s.oss_region):
        raise HTTPException(
            status_code=503,
            detail="Logo upload isn't configured yet (OSS credentials missing).",
        )
    endpoint = f"https://oss-{s.oss_region}.aliyuncs.com"
    auth = oss2.AuthV4(s.oss_access_key_id, s.oss_access_key_secret)
    # No network call here — just builds the client; signing is local crypto.
    return oss2.Bucket(auth, endpoint, s.oss_bucket, region=s.oss_region), s


@router.post("/logo-url", response_model=PresignedUploadResponse)
async def presign_logo_upload(
    payload: PresignedUploadRequest,
    merchant: MerchantDB = Depends(get_current_merchant),
):
    content_type = payload.content_type.lower().strip()
    if content_type not in _EXT:
        raise HTTPException(
            status_code=400,
            detail="Logo must be PNG, JPG, WebP, GIF, or SVG.",
        )

    bucket, s = _bucket()
    object_key = (
        f"logos/{merchant.id}/logo_{int(time.time())}_{uuid.uuid4().hex[:6]}"
        f".{_EXT[content_type]}"
    )
    # These headers are bound into the signature — the browser MUST send the
    # same ones on the PUT or OSS rejects it with SignatureNotMatch.
    required_headers = {
        "Content-Type": content_type,
        "x-oss-object-acl": "public-read",
    }

    try:
        upload_url = bucket.sign_url(
            "PUT", object_key, _UPLOAD_TTL, slash_safe=True, headers=required_headers
        )
    except Exception as e:
        logger.error(f"[upload] failed to sign URL for {merchant.id}: {e}")
        raise HTTPException(status_code=502, detail="Could not create an upload URL.")

    public_url = f"https://{s.oss_bucket}.oss-{s.oss_region}.aliyuncs.com/{object_key}"
    return PresignedUploadResponse(
        upload_url=upload_url,
        public_url=public_url,
        object_key=object_key,
        required_headers=required_headers,
    )
