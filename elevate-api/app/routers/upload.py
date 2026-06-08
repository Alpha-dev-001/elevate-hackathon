"""
OSS direct upload via STS tokens.
FastAPI never handles file bytes — only generates temporary credentials.
Frontend uploads directly to OSS bucket.
"""
import uuid
import time
from fastapi import APIRouter, HTTPException
from app.core.config import get_settings
from app.models.schemas import STSTokenResponse

router = APIRouter(prefix="/api/upload", tags=["upload"])


@router.post("/token", response_model=STSTokenResponse)
async def get_oss_upload_token(merchant_id: str):
    """
    Generate temporary STS credentials for direct OSS upload.
    Frontend uses these to upload logo directly — never through FastAPI.
    Credentials expire in 15 minutes.
    """
    settings = get_settings()

    # Object key pre-assigned — frontend uploads to this exact path
    object_key = f"logos/{merchant_id}/logo_{int(time.time())}.png"

    try:
        # TODO: Wire up real Alibaba Cloud STS SDK
        # import sts20150401.models as sts_models
        # from alibabacloud_sts20150401.client import Client
        # Real implementation goes here when credentials are available

        # For development: return mock credentials that work with local MinIO
        # or a development OSS bucket
        if settings.app_env == "development":
            return STSTokenResponse(
                access_key_id="dev_key",
                access_key_secret="dev_secret",
                security_token="dev_token",
                expiration=str(int(time.time()) + 900),
                bucket=settings.oss_bucket,
                region=settings.oss_region,
                object_key=object_key,
            )

        # Production: real STS call
        # Placeholder raises until real SDK is wired
        raise HTTPException(
            status_code=501,
            detail="STS credentials not configured — add Alibaba Cloud STS SDK"
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"STS token generation failed: {e}")


@router.get("/confirm")
async def confirm_upload(object_key: str, merchant_id: str):
    """
    Frontend calls this after successful OSS upload to confirm.
    Returns the public OSS URL for use in onboarding.
    """
    settings = get_settings()
    oss_url = (
        f"https://{settings.oss_bucket}.oss-{settings.oss_region}"
        f".aliyuncs.com/{object_key}"
    )
    return {"oss_url": oss_url, "object_key": object_key}
