# Stage 1: Builder
FROM python:3.9-slim AS builder
ENV VENV_PATH=/opt/venv
RUN python3 -m venv $VENV_PATH
ENV PATH="$VENV_PATH/bin:$PATH"

RUN apt-get update && apt-get install -y gcc build-essential && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY pyproject.toml LICENSE README.md /app/
COPY src ./src/
RUN pip install .

# Stage 2: Test Runner
FROM python:3.9-slim AS runner
ENV VENV_PATH=/opt/venv
ENV PATH="$VENV_PATH/bin:$PATH"
WORKDIR /app
COPY --from=builder /opt/venv /opt/venv
COPY --from=builder /app/src /app/src
RUN pip install pytest pytest-asyncio pytest-timeout redis
COPY src/panoseti_grpc/telemetry/telemetry_config.toml .
COPY tests ./tests
CMD ["python", "-m", "pytest", "--timeout=30", "-v", "tests/gnss_control"]
