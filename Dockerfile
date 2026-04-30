FROM python:3.12-alpine as base
WORKDIR /opt/hyperglass
ENV HYPERGLASS_APP_PATH=/etc/hyperglass
ENV HYPERGLASS_HOST=0.0.0.0
ENV HYPERGLASS_PORT=8001
ENV HYPERGLASS_DEBUG=false
ENV HYPERGLASS_DEV_MODE=false
ENV HYPERGLASS_REDIS_HOST=redis
ENV HYPEGLASS_DISABLE_UI=true
ENV HYPERGLASS_CONTAINER=true
RUN apk upgrade --no-cache && pip3 install --no-cache-dir --upgrade "setuptools>=78.1.1" pip
COPY . .

FROM base as ui
WORKDIR /opt/hyperglass/hyperglass/ui
RUN apk add build-base pkgconfig cairo-dev nodejs npm
RUN npm install -g pnpm
RUN pnpm install -P

# Pre-warm the Next.js build cache with a stub hyperglass.json so the
# runtime rebuild (which always fires because the operator's real
# config produces a different HYPERGLASS_BUILD_ID) starts with a hot
# SWC/webpack cache (.next/cache/) instead of cold-compiling every
# source file. The `out/` static export produced here is never served:
# hyperglass.frontend.build_frontend() overwrites it on container
# start before the HTTP listener binds. The `.env` build-id sentinel
# is also untouched, so the runtime never mistakes this stub build
# for a cache hit.
RUN echo '{}' > hyperglass.json && \
    NODE_OPTIONS=--openssl-legacy-provider NODE_ENV=production \
    node_modules/.bin/next build

FROM ui as hyperglass
WORKDIR /opt/hyperglass
RUN pip3 install -e .

EXPOSE ${HYPERGLASS_PORT}
CMD ["python3", "-m", "hyperglass.console", "start"]
