# syntax=docker/dockerfile:1.7
# ============================================================
# hh-auto-web — Next.js 16 standalone build
# Multi-stage build: deps → build → runtime
# ============================================================

# ---------- Stage 1: install deps with pnpm ----------
FROM node:22-alpine AS deps

RUN corepack enable && corepack prepare pnpm@10.33.3 --activate

WORKDIR /app
COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
RUN pnpm fetch --frozen-lockfile

COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
RUN pnpm install --offline --frozen-lockfile

# ---------- Stage 2: build ----------
FROM node:22-alpine AS builder

RUN corepack enable && corepack prepare pnpm@10.33.3 --activate

WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .

# rewrites() in next.config.ts uses this at build time to produce routing config.
# In docker-compose, the FastAPI app is reachable as "app:8100" on the default network.
ARG NEXT_PUBLIC_BACKEND_URL=http://app:8100
ENV NEXT_PUBLIC_BACKEND_URL=$NEXT_PUBLIC_BACKEND_URL

ENV NEXT_TELEMETRY_DISABLED=1
RUN pnpm build

# ---------- Stage 3: runtime ----------
FROM node:22-alpine AS runner

WORKDIR /app

ENV NODE_ENV=production
ENV NEXT_TELEMETRY_DISABLED=1
ENV PORT=3000
ENV HOSTNAME=0.0.0.0

# next/font requires public/ and .next/static at runtime
COPY --from=builder /app/public ./public
COPY --from=builder /app/.next/standalone ./
COPY --from=builder /app/.next/static ./.next/static

EXPOSE 3000

CMD ["node", "server.js"]
