# syntax=docker/dockerfile:1
# =============================================================================
# Image de l'interface (ECS Fargate, infrastructure/infra/web.tf).
#
# Construite par le job build_web de .github/workflows/app.yml (contexte
# app/web), poussee dans ECR avec le SHA court du commit comme tag. Sortie
# `standalone` de Next.js : server.js et le strict necessaire de node_modules.
# Le serveur lit sa configuration (AGENT_MODE, AWS_REGION, ALPHAFORGE_*) a
# chaque requete ; les identifiants AWS viennent du role de la tache.
#
# Images de base tirees de la galerie publique d'ECR : pas de limite de debit
# de Docker Hub sur les runners GitHub.
# =============================================================================

FROM public.ecr.aws/docker/library/node:24-slim AS deps
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund

FROM public.ecr.aws/docker/library/node:24-slim AS build
WORKDIR /app
ENV NEXT_TELEMETRY_DISABLED=1
COPY --from=deps /app/node_modules ./node_modules
COPY . .
RUN npm run build

FROM public.ecr.aws/docker/library/node:24-slim AS run
WORKDIR /app
ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    PORT=3000 \
    HOSTNAME=0.0.0.0
COPY --from=build --chown=node:node /app/.next/standalone ./
COPY --from=build --chown=node:node /app/.next/static ./.next/static
USER node
EXPOSE 3000
CMD ["node", "server.js"]
