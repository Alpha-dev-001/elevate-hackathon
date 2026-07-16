"""Mirroring a CSV/manual image_url to Elevate's own OSS bucket. Never
blocks or fails product creation — a mirror failure just leaves the
original external URL in place (best-effort, same philosophy as every
other background enrichment step in this codebase)."""
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import httpx


def _run(coro):
    return asyncio.run(coro)


class TestMirrorImage:
    def test_already_on_our_oss_bucket_is_a_noop(self):
        """An image already hosted on our own bucket must not be re-fetched
        and re-uploaded — that would just be a wasteful self-copy."""
        from app.services.image_mirror import mirror_image
        with patch("app.services.image_mirror.get_settings") as mock_settings:
            mock_settings.return_value.oss_bucket = "elevate-bucket"
            mock_settings.return_value.oss_region = "us-east-1"
            url = "https://elevate-bucket.oss-us-east-1.aliyuncs.com/products/m1/abc.jpg"
            result = _run(mirror_image(url, "m1"))
        assert result is None  # no-op signals "nothing to change"

    def test_successful_mirror_returns_new_oss_url(self):
        from app.services.image_mirror import mirror_image

        fake_response = MagicMock()
        fake_response.status_code = 200
        fake_response.headers = {"content-type": "image/jpeg"}
        fake_response.content = b"fake-image-bytes"

        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.get = AsyncMock(return_value=fake_response)

        mock_bucket = MagicMock()

        with (
            patch("app.services.image_mirror.httpx.AsyncClient", return_value=mock_client),
            patch("app.services.image_mirror._bucket", return_value=(mock_bucket, MagicMock(oss_bucket="elevate-bucket", oss_region="us-east-1"))),
        ):
            result = _run(mirror_image("https://example.com/photo.jpg", "m1"))

        assert result is not None
        assert result.startswith("https://elevate-bucket.oss-us-east-1.aliyuncs.com/products/m1/")
        mock_bucket.put_object.assert_called_once()

    def test_unreachable_source_returns_none(self):
        from app.services.image_mirror import mirror_image

        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.get = AsyncMock(side_effect=httpx.TimeoutException("timed out"))

        with patch("app.services.image_mirror.httpx.AsyncClient", return_value=mock_client):
            result = _run(mirror_image("https://example.com/dead.jpg", "m1"))
        assert result is None

    def test_non_image_content_type_returns_none(self):
        from app.services.image_mirror import mirror_image

        fake_response = MagicMock()
        fake_response.status_code = 200
        fake_response.headers = {"content-type": "text/html"}
        fake_response.content = b"<html></html>"

        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.get = AsyncMock(return_value=fake_response)

        with patch("app.services.image_mirror.httpx.AsyncClient", return_value=mock_client):
            result = _run(mirror_image("https://example.com/page.html", "m1"))
        assert result is None

    def test_4xx_response_returns_none(self):
        from app.services.image_mirror import mirror_image

        fake_response = MagicMock()
        fake_response.status_code = 404
        fake_response.headers = {"content-type": "text/html"}
        fake_response.content = b""

        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.get = AsyncMock(return_value=fake_response)

        with patch("app.services.image_mirror.httpx.AsyncClient", return_value=mock_client):
            result = _run(mirror_image("https://example.com/gone.jpg", "m1"))
        assert result is None

    def test_oss_not_configured_returns_none(self):
        """_bucket() raises HTTPException(503) when OSS credentials are
        missing — mirroring degrades to a no-op, never a crash."""
        from fastapi import HTTPException
        from app.services.image_mirror import mirror_image

        fake_response = MagicMock()
        fake_response.status_code = 200
        fake_response.headers = {"content-type": "image/jpeg"}
        fake_response.content = b"fake-image-bytes"

        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.get = AsyncMock(return_value=fake_response)

        with (
            patch("app.services.image_mirror.httpx.AsyncClient", return_value=mock_client),
            patch("app.services.image_mirror._bucket", side_effect=HTTPException(status_code=503, detail="not configured")),
        ):
            result = _run(mirror_image("https://example.com/photo.jpg", "m1"))
        assert result is None
