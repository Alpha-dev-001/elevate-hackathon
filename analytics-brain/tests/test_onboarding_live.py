"""
Live onboarding integration test — full stack, nothing mocked.

Hits a running server (port 9001) backed by real Postgres + Redis, fires the
real qwen-vl-max -> qwen-max pipeline, and listens on the real terminal
WebSocket for brand_ready. The logo is an Alibaba-hosted public image so the
VL model can fetch it.

Run the server first:
  ./.venv/Scripts/python.exe -m uvicorn app.main:app --port 9001
"""
import asyncio
import json
import time
import uuid

import httpx
import websockets

BASE = "http://127.0.0.1:9001"
WS = "ws://127.0.0.1:9001"
LOGO = "https://help-static-aliyun-doc.aliyuncs.com/file-manage-files/zh-CN/20241022/emyrja/dog_and_girl.jpeg"


async def main() -> int:
    email = f"live_{uuid.uuid4().hex[:8]}@example.com"
    with httpx.Client(base_url=BASE, timeout=30) as c:
        # 1. signup -> cookie + merchant_id
        r = c.post("/auth/signup", json={
            "email": email, "store_name": "Aurora Live", "password": "a-strong-password",
            "category": "home", "description": "Warm minimalist homeware",
        })
        assert r.status_code == 201, r.text
        merchant_id = r.json()["id"]
        slug = r.json()["slug"]
        cookie = r.cookies.get("elevate_session")
        print(f"1. signed up {merchant_id} (slug={slug})")

        # 2. brand not ready yet -> 409 with a phase
        r = c.get("/onboarding/brand")
        assert r.status_code == 409, r.text
        print(f"2. /onboarding/brand before start -> 409 ({r.json()['detail']})")

        # 3. connect terminal WS FIRST, then start (avoid missing the push)
        async with websockets.connect(f"{WS}/ws/terminal/{merchant_id}") as sock:
            print("3. terminal WS connected")

            r = c.post("/onboarding/start", json={"logo_oss_url": LOGO})
            assert r.status_code == 202, r.text
            assert r.json()["status"] == "generating"
            t0 = time.time()
            print("4. POST /onboarding/start -> 202 generating, pipeline running...")

            # 5. await brand_ready (first push = brand w/ deterministic icons)
            brand_pkg = None
            while time.time() - t0 < 90:
                raw = await asyncio.wait_for(sock.recv(), timeout=90)
                msg = json.loads(raw)
                if msg.get("event") != "brand_ready":
                    continue
                payload = msg["payload"]
                if "error" in payload:
                    print("   PIPELINE ERROR:", payload["error"]); return 1
                brand_pkg = payload["brand_package"]
                print(f"5. brand_ready received at {time.time()-t0:.1f}s")
                break
            assert brand_pkg is not None, "no brand_ready within 90s"

            # validate the shape the frontend will consume
            assert brand_pkg["brand"]["store_name"] == "Aurora Live"
            assert brand_pkg["brand"]["palette"]["accent"].startswith("#")
            rules = brand_pkg["guards"]["rules"]
            assert rules and rules[0]["warning_message"], "no guard warning"
            assert "<svg" in brand_pkg["brand"]["icons"]["logo_mark"]
            print(f"   palette: {brand_pkg['brand']['palette']}")
            print(f"   guard[0]: {rules[0]['warning_message'][:120]}")

            # 6. (optional) second push = upgraded SVG icons
            try:
                raw = await asyncio.wait_for(sock.recv(), timeout=30)
                msg = json.loads(raw)
                if msg.get("event") == "brand_ready" and "brand_package" in msg["payload"]:
                    print(f"6. icon-upgrade push received at {time.time()-t0:.1f}s "
                          f"(logo_mark {len(msg['payload']['brand_package']['brand']['icons']['logo_mark'])} chars)")
            except asyncio.TimeoutError:
                print("6. no icon-upgrade push (acceptable — deterministic marks stand)")

        # 7. GET /onboarding/brand now returns 200 (recovery/review path)
        r = c.get("/onboarding/brand")
        assert r.status_code == 200, r.text
        assert r.json()["store_shell_url"].endswith(f"/s/{slug}")
        print("7. GET /onboarding/brand -> 200 (durable, review-page ready)")

        # 8. publish -> live
        r = c.post("/onboarding/publish")
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["status"] == "live" and body["storefront_url"] == f"/s/{slug}"
        print(f"8. publish -> live at {body['storefront_url']}")

        # 9. /auth/me reflects the live status
        r = c.get("/auth/me")
        assert r.json()["is_live"] is True
        assert r.json()["onboarding_status"] == "live"
        print("9. merchant flipped live + onboarding_status=live")

    print("ALL ONBOARDING LIVE CHECKS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
