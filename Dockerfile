FROM node:24-bookworm-slim AS webui-builder

WORKDIR /app
COPY webui/package.json webui/package-lock.json ./webui/
WORKDIR /app/webui
RUN npm ci
COPY webui/ ./
RUN mkdir -p /app/mira/web && npm run build

FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

RUN apt-get update && \
    apt-get install -y --no-install-recommends ca-certificates git bubblewrap openssh-client libmagic1 && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Keep the runtime environment writable by the non-root mira user. Enabled
# channels may install their manifest-declared dependencies at startup.
ENV VIRTUAL_ENV=/app/.venv
ENV PATH="/app/.venv/bin:$PATH"
RUN uv venv --seed "$VIRTUAL_ENV"

# Install Python dependencies first (cached layer). Hatch reads the custom build
# hook from hatch_build.py even for this metadata-only install.
ARG NANOBOT_EXTRAS=
COPY pyproject.toml README.md LICENSE THIRD_PARTY_NOTICES.md hatch_build.py ./
RUN mkdir -p mira && touch mira/__init__.py && \
    if [ -n "$NANOBOT_EXTRAS" ]; then \
        NANOBOT_SKIP_WEBUI_BUILD=1 uv pip install \
            --python "$VIRTUAL_ENV/bin/python" --no-cache ".[${NANOBOT_EXTRAS}]"; \
    else \
        NANOBOT_SKIP_WEBUI_BUILD=1 uv pip install \
            --python "$VIRTUAL_ENV/bin/python" --no-cache .; \
    fi && \
    rm -rf mira

# Copy the full source and install
COPY mira/ mira/
COPY scripts/install_channel_dependencies.py scripts/
COPY --from=webui-builder /app/mira/web/dist/ mira/web/dist/
RUN NANOBOT_SKIP_WEBUI_BUILD=1 uv pip install --python "$VIRTUAL_ENV/bin/python" --no-cache .

# Preinstall selected channel dependencies from their manifests. A comma-separated
# list keeps the image configurable while preserving WhatsApp in the default image.
ARG MIRA_CHANNELS=whatsapp
ARG NANOBOT_CHANNELS=
RUN selected_channels="${MIRA_CHANNELS:-${NANOBOT_CHANNELS:-whatsapp}}"; \
    for channel in $(printf '%s' "$selected_channels" | tr ',' ' '); do \
        python -m scripts.install_channel_dependencies "$channel"; \
    done

# Render deploy template (see render.yaml): committed gateway config that wires
# secrets through ${ANTHROPIC_API_KEY} / ${NANOBOT_WEB_TOKEN} env vars (resolved
# at startup). Lives in the code dir (/app), not the data dir, so a mounted disk
# won't shadow it. Only used when RENDER=true; ignored by local runs.
COPY render-config.json ./

# Create the non-root user and hand ownership of the writable virtualenv to it.
RUN useradd -m -u 1000 -s /bin/bash mira && \
    mkdir -p /home/mira/.mira && \
    chown -R mira:mira /home/mira /app/.venv

COPY entrypoint.sh /usr/local/bin/entrypoint.sh
RUN sed -i 's/\r$//' /usr/local/bin/entrypoint.sh && chmod +x /usr/local/bin/entrypoint.sh

# Start as root so the entrypoint can chown the data dir (on Render, the
# freshly-mounted root-owned persistent disk) before dropping to the non-root
# mira user via setpriv. The entrypoint drops privileges on every root start
# and fails closed if it cannot, so the agent never runs as root (see
# entrypoint.sh).
USER root
ENV HOME=/home/mira
# Ensure crash output reaches Render logs (app output is otherwise swallowed on
# non-graceful exit).
ENV PYTHONUNBUFFERED=1 PYTHONFAULTHANDLER=1

# Gateway health endpoint and optional WebUI/WebSocket channel ports
EXPOSE 18790 8765

ENTRYPOINT ["entrypoint.sh"]
CMD ["status"]
