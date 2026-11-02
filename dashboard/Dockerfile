# syntax=docker/dockerfile:1.7
# Self-hosted alternative to Vercel. Build context: dashboard/
FROM node:22-bookworm-slim AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY . .
# NEXT_PUBLIC_* values are inlined at build time.
ARG NEXT_PUBLIC_DUNE_NAMESPACE=
ENV NEXT_OUTPUT=standalone NEXT_TELEMETRY_DISABLED=1 \
    NEXT_PUBLIC_DUNE_NAMESPACE=${NEXT_PUBLIC_DUNE_NAMESPACE}
RUN npm run build

FROM node:22-bookworm-slim
WORKDIR /app
ENV NODE_ENV=production NEXT_TELEMETRY_DISABLED=1 PORT=3000 HOSTNAME=0.0.0.0
COPY --from=build --chown=node:node /app/.next/standalone ./
COPY --from=build --chown=node:node /app/.next/static ./.next/static
COPY --from=build --chown=node:node /app/data ./data
USER node
EXPOSE 3000
CMD ["node", "server.js"]
