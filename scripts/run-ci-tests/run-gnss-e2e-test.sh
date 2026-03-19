#!/bin/bash
set -e

COMPOSE_FILE="../../tests/gnss_control/docker-compose.e2e.yml"

echo "--- Building GNSS E2E Environment ---"
docker compose -f $COMPOSE_FILE build

echo "--- Running GNSS E2E Tests ---"
docker compose -f $COMPOSE_FILE up \
    --build \
    --exit-code-from test_runner \
    --abort-on-container-exit

echo "--- Cleaning Up ---"
docker compose -f $COMPOSE_FILE down --volumes --remove-orphans

echo "--- GNSS E2E Run Completed Successfully ---"
