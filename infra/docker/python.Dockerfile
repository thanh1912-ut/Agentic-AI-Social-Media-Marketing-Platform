FROM golang:1.26-alpine AS facebook-cli-builder
WORKDIR /src
COPY services/research/facebook_cli_runner/go.mod services/research/facebook_cli_runner/go.sum ./
COPY services/research/facebook_cli_runner/main.go ./
RUN mkdir -p /out && go build -trimpath -ldflags="-s -w" -o /out/facebook-cli-runner .

FROM python:3.12-slim

ARG INSTALL_DOCLING=0

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app
COPY pyproject.toml README.md ./
COPY packages ./packages
COPY services ./services
COPY database ./database
COPY scripts ./scripts
COPY alembic.ini ./
RUN pip install --upgrade pip && if [ "$INSTALL_DOCLING" = "1" ]; then pip install '.[docling]'; else pip install .; fi
COPY --from=facebook-cli-builder /out/facebook-cli-runner /usr/local/bin/facebook-cli-runner
ENV FACEBOOK_CLI_RUNNER_PATH=/usr/local/bin/facebook-cli-runner
