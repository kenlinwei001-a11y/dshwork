# syntax=docker/dockerfile:1
# WorkDSH 浏览器模式（Linux 容器）。构建上下文必须是仓库根：
#   docker build -f deploy/docker/Dockerfile -t workdsh:local .
#   docker run -d --name workdsh -p 127.0.0.1:18989:18989 -v workdsh-data:/data workdsh:local
# 可选构建参数：INSTALL_CHROMIUM=1（Playwright MCP 需要，镜像约 +400MB）
FROM node:24-bookworm-slim

ARG INSTALL_CHROMIUM=0
ENV DEBIAN_FRONTEND=noninteractive \
    HOME=/data/home \
    APP_DIR=/app \
    WORKDSH_PREVIEW_HOME=/data/dsh \
    DSH_AGENTS_HOME=/data/agents \
    WORKDSH_PREVIEW_PORT=18989 \
    WORKDSH_PREVIEW_HOST=0.0.0.0 \
    WORKDSH_PREVIEW_HEAP_MB=4096 \
    MCP_SERVERS_ROOT=/opt/mcp-servers \
    SEMANTICA_VENV=/opt/venvs/semantica \
    SEED_SKILLS_DIR=/seed/.agents/skills

RUN apt-get update && apt-get install -y --no-install-recommends \
      git curl ca-certificates python3 python3-venv python3-dev build-essential patch procps tini \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY . .
RUN rm -rf .git .test-runtime .artifacts

WORKDIR /app/apps/web
RUN corepack enable && corepack pnpm install --frozen-lockfile && corepack pnpm build

WORKDIR /app
RUN HOME=/seed bash knowledge/setup.sh
RUN MCP_SERVERS_ROOT=/opt/mcp-servers bash deploy/scripts/install-mcp-servers.sh
RUN SEMANTICA_PYTHON=python3 SEMANTICA_VENV=/opt/venvs/semantica bash deploy/scripts/install-semantica-mcp.sh

RUN if [ "$INSTALL_CHROMIUM" = "1" ]; then \
      npx -y playwright@1.48.2 install --with-deps chromium && rm -rf /root/.npm; \
    fi

COPY deploy/docker/entrypoint.sh /usr/local/bin/entrypoint.sh
COPY deploy/docker/healthcheck.sh /usr/local/bin/healthcheck.sh
RUN chmod 0755 /usr/local/bin/entrypoint.sh /usr/local/bin/healthcheck.sh \
    && mkdir -p /data/dsh /data/agents /data/home

VOLUME ["/data"]
EXPOSE 18989
HEALTHCHECK --interval=30s --timeout=5s --start-period=120s --retries=3 \
  CMD ["/usr/local/bin/healthcheck.sh"]

ENTRYPOINT ["/usr/bin/tini", "--", "/usr/local/bin/entrypoint.sh"]
