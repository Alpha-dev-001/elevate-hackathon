# Elevate — Your store, alive.

> Autonomous merchant intelligence. Your store works with you 24/7.

[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](./LICENSE)
[![Built with Qwen Cloud](https://img.shields.io/badge/Built%20with-Qwen%20Cloud-blue)](https://qwencloud.com)
[![Alibaba Cloud](https://img.shields.io/badge/Deployed%20on-Alibaba%20Cloud-orange)](https://alibabacloud.com)

---

## What is Elevate?

Most merchant tools treat AI like a chatbot. You ask, it answers, you act.

Elevate flips that entirely. Upload your logo — Elevate builds your store,
brands it, and starts running it. It watches what customers do, translates
signals into decisions, and acts the moment you approve. No chat. No reports.
Just your store working with you.

---

## Stack

| Layer | Technology |
|-------|-----------|
| Frontend | Next.js 15, TypeScript, Tailwind, Framer Motion |
| Backend | FastAPI, Python 3.10, Pydantic v2 |
| AI | Qwen Cloud |
| Infrastructure | Alibaba Cloud Function Compute, Redis, RDS, OSS |
| Deploy | Serverless Devs |

---

## Getting Started

```bash
# Clone
git clone https://github.com/Alpha-dev-001/elevate
cd elevate

# Backend
cd analytics-brain
cp .env.example .env
pip install -r requirements.txt
uvicorn app.main:app --reload

# Frontend
cd ../storefront-ui
cp .env.example .env.local
npm install
npm run dev
```

---

## Hackathon

Built for the **Global AI Hackathon Series with Qwen Cloud** — Track 4: Autopilot Agent.

---

## License

MIT — see [LICENSE](./LICENSE)
