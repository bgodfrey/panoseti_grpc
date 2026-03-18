#!/bin/bash
set -e

# Define the compose file to use
COMPOSE_FILE="tests/gnss_control/docker-compose.test.yml"

echo "--- Building GNSS Control CI Environment ---"
docker compose -f $COMPOSE_FILE build

echo "--- Running GNSS Control Logging Tests ---"
# 1. 'up': Starts Redis and the Test Runner
# 2. '--exit-code-from test_runner': If pytest fails, the script exits with error
# 3. '--abort-on-container-exit': Stops Redis as soon as tests finish
docker compose -f $COMPOSE_FILE up \
    --build \
    --exit-code-from test_runner \
    --abort-on-container-exit

echo "--- Cleaning Up ---"
docker compose -f $COMPOSE_FILE down --volumes --remove-orphans

echo "--- GNSS Control CI Run Completed Successfully ---"
