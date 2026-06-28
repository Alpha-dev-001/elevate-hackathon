# Deploying Elevate to Alibaba Cloud

> Goal: satisfy the hackathon requirement — **backend running on Alibaba Cloud
> Function Compute** — plus the managed data services it needs. This is a
> from-zero guide. Nothing is deployed yet (the repo has only `Dockerfile.dev`
> and no `s.yaml`; this guide adds production artifacts).

**Current status:** ❌ Not deployed. Local dev runs via `docker compose up`.
**Hackathon needs:** backend on Function Compute + a short screen recording proving it.

---

## 0. The shape of the deployment

```
                       ┌─────────────────────────────┐
  Browser ── HTTPS ──► │ Frontend (Next.js)          │
                       │  Function Compute (web fn)   │
                       └──────────────┬──────────────┘
                                      │  HTTPS / WSS
                       ┌──────────────▼──────────────┐
                       │ Backend (FastAPI)            │
                       │  Function Compute (api fn)   │
                       │  provisioned concurrency = 1 │  ← no cold start in demo
                       └───┬────────┬────────┬────────┘
              ┌────────────┘        │        └────────────┐
     ┌────────▼───────┐   ┌─────────▼──────┐   ┌──────────▼─────────┐
     │ ApsaraDB RDS   │   │ Tair (Redis)   │   │ OSS bucket         │
     │ PostgreSQL     │   │ key-value      │   │ logo uploads       │
     └────────────────┘   └────────────────┘   └────────────────────┘
                                      │
                       ┌──────────────▼──────────────┐
                       │ Model Studio / DashScope     │  qwen-vl-max + qwen-max
                       └─────────────────────────────┘
```

You need **5 cloud resources**: RDS Postgres, Tair Redis, an OSS bucket, a Model
Studio API key (Qwen), and Function Compute for the two functions.

---

## 1. Prerequisites (do once)

1. **Alibaba Cloud account** + claim your hackathon credits ($3,000 cloud credits
   per track winner; sign-up credits otherwise). Console: https://account.alibabacloud.com
2. Pick **one region** and use it for everything (lower latency, simpler). The repo
   defaults reference `cn-hongkong` — good for international access. Use it unless
   you have a reason not to.
3. Install the CLIs:
   ```bash
   # Serverless Devs — the Function Compute deploy tool ("s")
   npm install -g @serverless-devs/s
   # Alibaba Cloud CLI (for RDS/Tair/OSS scripting; optional, console works too)
   # https://www.alibabacloud.com/help/en/cli
   ```
4. Create a **RAM user** with an AccessKey (don't use the root account key):
   Console → RAM → Users → Create User → grant `AliyunFCFullAccess`,
   `AliyunOSSFullAccess`, `AliyunRDSFullAccess`, `AliyunRedisFullAccess`.
   Save the **AccessKey ID** and **Secret**.
5. Configure Serverless Devs with that key:
   ```bash
   s config add
   # choose "Alibaba Cloud (alibaba)", paste AccessKeyID + AccessKeySecret
   ```

---

## 2. Provision the managed services

### 2a. Model Studio (Qwen) API key
- Console → **Model Studio** (a.k.a. DashScope) → enable it → API-Key → create.
- This is your `QWEN_API_KEY`.
- `QWEN_API_BASE` for the international endpoint:
  `https://dashscope-intl.aliyuncs.com/compatible-mode/v1`
  (mainland endpoint: `https://dashscope.aliyuncs.com/compatible-mode/v1`)
- `QWEN_MODEL=qwen-max`. (The VL model id `qwen-vl-max` is referenced in
  `config.py` as `qwen_vl_model` — confirm both are enabled in your account.)

### 2b. OSS bucket (logo uploads)
- Console → **OSS** → create bucket, same region, ACL = **public-read** (logos are
  fetched by qwen-vl-max and shown in the store).
- Note `OSS_BUCKET`, `OSS_REGION` (e.g. `oss-cn-hongkong`).
- The RAM user's AccessKey doubles as `OSS_ACCESS_KEY_ID` / `OSS_ACCESS_KEY_SECRET`.
- Add a **CORS rule** so the browser can PUT directly: allow `PUT, GET`, origin =
  your frontend URL, headers = `*`.

### 2c. ApsaraDB RDS for PostgreSQL
- Console → **ApsaraDB RDS** → create instance, engine **PostgreSQL 16**, same region.
- Create a database `elevate` and an account.
- Whitelist: allow access from Function Compute (set the instance's network to the
  same VPC as your FC functions, or temporarily `0.0.0.0/0` for the demo — tighten after).
- Build `DATABASE_URL`:
  `postgresql+asyncpg://USER:PASSWORD@HOST:5432/elevate`
- Apply the schema. The app calls `Base.metadata.create_all` on startup for fresh
  DBs; also run the sprint-3 migration for safety:
  ```bash
  psql "postgresql://USER:PASSWORD@HOST:5432/elevate" -f analytics-brain/migrations/2026_sprint3.sql
  ```

### 2d. Tair (Redis-compatible)
- Console → **Tair** (or ApsaraDB for Redis) → create instance, same region/VPC.
- Note `REDIS_HOST`, `REDIS_PORT` (6379), and set a password → `REDIS_PASSWORD`.

---

## 3. Production container images

The repo only ships `Dockerfile.dev` (hot-reload). This guide adds
`analytics-brain/Dockerfile` (production). Function Compute runs **custom
container** functions, so you push images to **ACR** (Container Registry).

1. Console → **Container Registry (ACR)** → create a namespace, e.g. `elevate`.
2. Build + push the backend (replace `<region>` and `<namespace>`):
   ```bash
   REG=registry.<region>.aliyuncs.com/<namespace>
   docker build -t $REG/bms-backend-brain:latest ./analytics-brain
   docker login --username=<your-aliyun-account> registry.<region>.aliyuncs.com
   docker push $REG/bms-backend-brain:latest
   ```
3. Same for the frontend if you host it on FC (see §5).

> Production `Dockerfile`s for both services are added alongside this guide
> (`analytics-brain/Dockerfile`). They run uvicorn/next without the `--reload`
> volume mounts.

---

## 4. Deploy the backend to Function Compute

A starter `s.yaml` is added at the repo root. Fill in your region, image, and the
env vars from §2, then:

```bash
s deploy
```

Key points baked into `s.yaml`:
- **Custom-container** runtime pointing at your ACR image.
- **HTTP trigger** (anonymous auth) so the browser can reach it.
- **provisionConfig target: 1** — one instance always warm, so the 4-second cold
  start never kills the demo (CLAUDE.md requirement).
- **Port 9000**, `caPort: 9000` (FC must know the container's listen port).
- All secrets as `environmentVariables` (never bake them into the image).

After deploy, `s` prints the function's public URL, e.g.
`https://bms-backend-brain.<region>.fcapp.run`. That is your `BASE_URL`.

### WebSockets
FastAPI's WS pipeline needs a WS-capable entrypoint. FC HTTP triggers support
WebSocket for custom containers. If you hit issues, the fallback is **API Gateway**
in front of FC for the `/ws` route (CLAUDE.md references
`wss://elevate-gateway.<region>.alicloudapi.com/ws`). For the hackathon demo, the
direct `fcapp.run` URL with `wss://` usually works — test it early.

---

## 5. Deploy the frontend

Two options:

**Option A — Function Compute (keeps everything serverless, matches the diagram).**
Add a `web` function to `s.yaml` (a stub is included, commented). Set
`NEXT_PUBLIC_*` env vars to point at the backend URL, build the production image
(`storefront-ui/Dockerfile`), push to ACR, `s deploy`.

**Option B — Vercel / static (fastest to get a public URL).** Next.js deploys to
Vercel in minutes; point its env at your FC backend URL. This does **not** satisfy
"backend on Alibaba" by itself, but the *backend* requirement is already met by §4 —
the frontend can live anywhere. For least friction during the hackathon, do the
backend on FC (required) and the frontend wherever is quickest.

Set these on the frontend (see `storefront-ui/.env.local` for the local shape):
```
NEXT_PUBLIC_API_BASE=https://bms-backend-brain.<region>.fcapp.run
NEXT_PUBLIC_WS_URL=wss://bms-backend-brain.<region>.fcapp.run/ws
```

---

## 6. Environment variables (backend) — the full list

Copy `analytics-brain/.env` shape into the FC function's `environmentVariables`:

| Key | Where it comes from |
|-----|---------------------|
| `APP_ENV` | `production` |
| `DATABASE_URL` | §2c RDS |
| `REDIS_HOST` / `REDIS_PORT` / `REDIS_PASSWORD` | §2d Tair |
| `OSS_BUCKET` / `OSS_REGION` / `OSS_ACCESS_KEY_ID` / `OSS_ACCESS_KEY_SECRET` | §2b OSS + RAM key |
| `QWEN_API_KEY` / `QWEN_API_BASE` / `QWEN_MODEL` | §2a Model Studio |
| `JWT_SECRET` | generate a long random string |
| `BASE_URL` | the FC backend URL |
| `FRONTEND_URL` / `CORS_ORIGINS` | the frontend URL(s) |

---

## 7. Verify + record the proof

1. Health check: `curl https://bms-backend-brain.<region>.fcapp.run/api/health`
   (or whatever health route exists — check `app/main.py` / routers).
2. Open the frontend, run the onboarding → StoreBirth → builder → publish → live
   store → terminal decision → approve flow end to end.
3. **Screen-record** the FC console showing the function running + an invocation,
   and the live store URL. That recording is a hard submission requirement.

---

## 8. Logs & debugging in production

FC has no SSH. Logs flow to **SLS (Simple Log Service)**:
```bash
s logs --tail            # tail the deployed function's logs
```
Or in the FC console → your function → Logs. `config.py`/`s.yaml` can wire an SLS
project + logstore (`logConfig`) so invocations and errors are queryable.

---

## 9. Cost control (you're on credits)

- **Provisioned concurrency = 1** keeps one warm instance — small steady cost, but
  essential for the demo. Turn it to 0 when not demoing.
- RDS + Tair are the main ongoing spend — pick the smallest instance classes.
- Set a **budget alert** (Billing → Budgets) so credits don't evaporate silently.
- Tear down RDS/Tair after the hackathon if you're not continuing.

---

## Quick checklist

- [ ] Model Studio API key works (`qwen-max` + `qwen-vl-max` enabled)
- [ ] OSS bucket created, public-read, CORS allows browser PUT
- [ ] RDS Postgres reachable; `2026_sprint3.sql` applied
- [ ] Tair Redis reachable
- [ ] Backend image pushed to ACR
- [ ] `s deploy` succeeds; backend URL responds
- [ ] Provisioned concurrency = 1
- [ ] Frontend deployed, env points at backend
- [ ] End-to-end demo flow works on the cloud URLs
- [ ] Screen recording of FC running captured
