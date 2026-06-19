#!/usr/bin/env bash
# scripts/deploy.sh
# Manual deployment helper (use CI/CD pipeline for production).
# Builds the Docker image, pushes to ECR, runs migrations, updates ECS service.
#
# Usage:
#   ./scripts/deploy.sh dev
#   ./scripts/deploy.sh prod

set -euo pipefail

ENVIRONMENT=${1:-dev}
AWS_REGION=${AWS_REGION:-us-east-1}
GIT_SHA=$(git rev-parse --short HEAD)
TIMESTAMP=$(date +%Y%m%d-%H%M%S)
IMAGE_TAG="${GIT_SHA}-${TIMESTAMP}"

# Resolve names by environment
case "${ENVIRONMENT}" in
  prod|production)
    CLUSTER="noteflow-production-cluster"
    SERVICE="noteflow-production-api"
    TASK_DEF="noteflow-production-api"
    ;;
  dev|development)
    CLUSTER="noteflow-dev-cluster"
    SERVICE="noteflow-dev-api"
    TASK_DEF="noteflow-dev-api"
    ;;
  *)
    echo "Unknown environment: ${ENVIRONMENT}"; exit 1;;
esac

echo "╔══════════════════════════════════════╗"
echo "║  NoteFlow Deploy — ${ENVIRONMENT}   "
echo "║  Tag: ${IMAGE_TAG}                  "
echo "╚══════════════════════════════════════╝"

# ── 1. AWS Authentication ─────────────────────────────────────────

AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
ECR_REGISTRY="${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com"
ECR_REPO="${ECR_REGISTRY}/noteflow-${ENVIRONMENT}/api"

echo ""
echo "[1/5] Logging in to ECR..."
aws ecr get-login-password --region "${AWS_REGION}" | \
  docker login --username AWS --password-stdin "${ECR_REGISTRY}"

# ── 2. Build & Push ───────────────────────────────────────────────

echo ""
echo "[2/5] Building Docker image..."
docker build \
  --file infrastructure/docker/Dockerfile.api \
  --tag  "${ECR_REPO}:${IMAGE_TAG}" \
  --tag  "${ECR_REPO}:latest" \
  --build-arg BUILD_DATE="$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
  --build-arg GIT_SHA="${GIT_SHA}" \
  --cache-from "${ECR_REPO}:latest" \
  backend/

echo ""
echo "[3/5] Pushing image to ECR..."
docker push "${ECR_REPO}:${IMAGE_TAG}"
docker push "${ECR_REPO}:latest"
echo "  ✓ Pushed ${ECR_REPO}:${IMAGE_TAG}"

# ── 3. Get network config from existing service ───────────────────

echo ""
echo "[4/5] Running database migrations..."

NETWORK_CONFIG=$(aws ecs describe-services \
  --cluster "${CLUSTER}" \
  --services "${SERVICE}" \
  --query 'services[0].networkConfiguration' \
  --output json)

MIGRATION_TASK=$(aws ecs run-task \
  --cluster "${CLUSTER}" \
  --task-definition "${TASK_DEF}" \
  --launch-type FARGATE \
  --network-configuration "${NETWORK_CONFIG}" \
  --overrides '{"containerOverrides":[{"name":"api","command":["alembic","upgrade","head"]}]}' \
  --query 'tasks[0].taskArn' \
  --output text)

echo "  Migration task: ${MIGRATION_TASK}"
echo "  Waiting for migrations to complete..."

aws ecs wait tasks-stopped \
  --cluster "${CLUSTER}" \
  --tasks "${MIGRATION_TASK}"

EXIT_CODE=$(aws ecs describe-tasks \
  --cluster "${CLUSTER}" \
  --tasks "${MIGRATION_TASK}" \
  --query 'tasks[0].containers[0].exitCode' \
  --output text)

if [ "${EXIT_CODE}" != "0" ]; then
  echo "  ✗ Migration failed (exit code ${EXIT_CODE})"
  exit 1
fi
echo "  ✓ Migrations applied"

# ── 4. Deploy ECS Service ─────────────────────────────────────────

echo ""
echo "[5/5] Deploying to ECS..."

aws ecs update-service \
  --cluster  "${CLUSTER}" \
  --service  "${SERVICE}" \
  --force-new-deployment \
  --output json | jq -r '.service.deployments[0] | "  Deployment: \(.id) (\(.status))"'

echo "  Waiting for service stability (this may take 2–5 minutes)..."

aws ecs wait services-stable \
  --cluster  "${CLUSTER}" \
  --services "${SERVICE}"

echo ""
echo "╔══════════════════════════════════════╗"
echo "║  ✓ Deploy complete!                  "
echo "║  Environment : ${ENVIRONMENT}        "
echo "║  Image tag   : ${IMAGE_TAG}          "
echo "╚══════════════════════════════════════╝"
