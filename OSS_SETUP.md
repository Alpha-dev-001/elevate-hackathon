# OSS Setup — Logo / Asset Storage

This unblocks direct logo/asset upload. The backend never touches file bytes:
it signs a short-lived upload URL, and the browser uploads straight to OSS.

**Recommended approach: presigned PUT URLs (no RAM role, no STS).** Simpler than
the AssumeRole/STS dance and just as safe — the signed URL is scoped to one
object, one operation (PUT), and expires in ~15 minutes. You only need a bucket,
a RAM user with an AccessKey, and a small upload-only policy on that user.

You can either follow the steps and drop the values into `analytics-brain/.env`,
**or** paste the three values into the chat and I'll place them (`.env` is
gitignored — nothing leaks).

---

## Recommended region: `cn-hongkong` (China — Hong Kong)

- Matches the planned Function Compute region (`bms-backend-brain.cn-hongkong`).
- Internationally accessible.
- The logo is fetched **by URL** by qwen-vl-max; cross-region public fetch is
  already confirmed working, so bucket region and model region need not match.

Use the same region string everywhere: `cn-hongkong`.

---

## Step 1 — Create the bucket (KEEP IT PRIVATE)

[OSS console](https://oss.console.aliyun.com) → **Create Bucket**
- **Name:** `elevate-assets` (globally unique; if taken, pick another and tell me)
- **Region:** China (Hong Kong) — `cn-hongkong`
- **ACL:** **Private** ← do NOT make the bucket public. The scary warning is
  correct. We make individual *objects* public-read at upload time instead, so
  the bucket itself never exposes a listing or anything else.

## Step 2 — Add CORS to the bucket (don't skip — browser upload fails without it)

Bucket → **Content Security → CORS** → Create Rule:
- **Allowed Origins:** `http://localhost:3000` (add the production URL later)
- **Allowed Methods:** `PUT, POST, GET`
- **Allowed Headers:** `*`
- **Expose Headers:** `ETag`

## Step 3 — Create a RAM user + AccessKey

[RAM console](https://ram.console.aliyun.com) → **Identities → Users → Create User**
- Tick **Permanent AccessKey** ("Create an AccessKey ID and Secret for API or
  SDK access") — that's the programmatic-access option.
- Copy the **AccessKey ID** and **AccessKey Secret** (secret shown once).
  → `OSS_ACCESS_KEY_ID` / `OSS_ACCESS_KEY_SECRET`

## Step 4 — Attach an upload-only policy to that USER

RAM console → **Policies → Create Policy** → JSON, paste:

```json
{
  "Version": "1",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": ["oss:PutObject", "oss:PutObjectAcl"],
      "Resource": ["acs:oss:*:*:elevate-assets/*"]
    }
  ]
}
```

Then go to the **user** from Step 3 → **Permissions → Grant Permission** →
attach this policy. (`PutObjectAcl` lets the upload mark the object public-read
so the storefront and the vision model can read it, while the bucket stays
private.)

> That's it — no RAM role, no trust policy, no `AliyunSTSAssumeRoleAccess`.
> If you'd already started creating the role, you can abandon it; the trust
> policy you saw was correct but it isn't needed for the presigned-URL approach.

---

## Where the values go

Drop these into `analytics-brain/.env` (gitignored):

```dotenv
OSS_REGION=cn-hongkong
OSS_BUCKET=elevate-assets
OSS_ACCESS_KEY_ID=<from step 3>
OSS_ACCESS_KEY_SECRET=<from step 3>
```

Three secrets + the region/bucket. No role ARN needed.

## What I do once these land

1. Replace the mock STS endpoint in `routers/upload.py` with a presigned PUT
   URL signed by the RAM user's key (15-min expiry, scoped to one object key,
   forces `x-oss-object-acl: public-read` so the object is readable but the
   bucket isn't).
2. Swap the frontend logo step from the dev "paste a URL" input to a real
   drag-and-drop that PUTs straight to the signed URL.
3. Verify end-to-end: drop a logo → object public-read → brand generation.

---

### Alternative: STS/AssumeRole (only if you specifically want it)

The original CLAUDE.md design used STS temporary credentials. It's more moving
parts (a RAM role + trust policy + `AliyunSTSAssumeRoleAccess` on the user +
`OSS_ROLE_ARN`) for the same security property. Presigned URLs are the
recommended default; say the word if you'd rather go the STS route and I'll
adjust the doc and the endpoint.
