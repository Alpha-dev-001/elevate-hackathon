# Production image for the Next.js storefront on Alibaba Cloud Function Compute
# (custom container). Uses Next's `output: 'standalone'` (see next.config.js) for
# a minimal self-contained server. No volume mounts, no --reload.
#
# NOTE: NEXT_PUBLIC_* are inlined into the client bundle at BUILD time, so the
# backend URL must be passed as build args, not runtime env. Names must match
# what the app reads (lib/api.ts: NEXT_PUBLIC_API_URL, NEXT_PUBLIC_WS_URL):
#   docker build \
#     --build-arg NEXT_PUBLIC_API_URL=https://bms-backend-brain.cn-hongkong.fcapp.run \
#     --build-arg NEXT_PUBLIC_WS_URL=wss://bms-backend-brain.cn-hongkong.fcapp.run/ws \
#     -t <acr>/bms-frontend:latest ./storefront-ui

FROM node:20-alpine AS deps
WORKDIR /app
COPY package*.json ./
RUN npm ci || npm install

FROM node:20-alpine AS builder
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .
ARG NEXT_PUBLIC_API_URL
ARG NEXT_PUBLIC_WS_URL
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL
ENV NEXT_PUBLIC_WS_URL=$NEXT_PUBLIC_WS_URL
ENV NEXT_TELEMETRY_DISABLED=1
RUN npm run build

FROM node:20-alpine AS runner
WORKDIR /app
ENV NODE_ENV=production NEXT_TELEMETRY_DISABLED=1 PORT=3000 HOSTNAME=0.0.0.0
# Standalone output bundles a minimal server + its own node_modules.
COPY --from=builder /app/.next/standalone ./
COPY --from=builder /app/.next/static ./.next/static
EXPOSE 3000
CMD ["node", "server.js"]
