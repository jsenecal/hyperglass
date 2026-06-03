FROM python:3.12-alpine AS base
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

FROM base AS ui
WORKDIR /opt/hyperglass/hyperglass/ui
# linux-headers: psutil (no musl wheel) compiles from source and needs kernel
# headers; previously provided transitively by the removed cairo-dev chain.
RUN apk add build-base linux-headers nodejs npm
RUN npm install -g pnpm
RUN pnpm install -P

FROM ui AS hyperglass
LABEL org.opencontainers.image.title="hyperglass-ng" \
      org.opencontainers.image.description="hyperglass-ng — maintained fork of the hyperglass network looking glass" \
      org.opencontainers.image.source="https://github.com/jsenecal/hyperglass" \
      org.opencontainers.image.licenses="BSD-3-Clause-Clear"
WORKDIR /opt/hyperglass
RUN pip3 install -e .

EXPOSE ${HYPERGLASS_PORT}
CMD ["python3", "-m", "hyperglass.console", "start"]
