#!/usr/bin/env bash
# scripts/bootstrap-tfstate.sh
# Run ONCE per AWS account to create the Terraform remote state backend.
# Requires: AWS CLI configured with admin credentials.
#
# Usage:
#   ./scripts/bootstrap-tfstate.sh dev us-east-1
#   ./scripts/bootstrap-tfstate.sh prod us-east-1

set -euo pipefail

ENVIRONMENT=${1:-dev}
REGION=${2:-us-east-1}
BUCKET="noteflow-terraform-state-${ENVIRONMENT}"
TABLE="noteflow-terraform-locks"

echo "=== NoteFlow Terraform Bootstrap ==="
echo "Environment : ${ENVIRONMENT}"
echo "Region      : ${REGION}"
echo "State bucket: ${BUCKET}"
echo "Lock table  : ${TABLE}"
echo ""

# ── S3 State Bucket ───────────────────────────────────────────────

echo "Creating S3 state bucket..."
if aws s3api head-bucket --bucket "${BUCKET}" --region "${REGION}" 2>/dev/null; then
  echo "  Bucket ${BUCKET} already exists — skipping"
else
  aws s3api create-bucket \
    --bucket "${BUCKET}" \
    --region "${REGION}" \
    $([ "${REGION}" != "us-east-1" ] && echo "--create-bucket-configuration LocationConstraint=${REGION}" || true)

  # Block all public access
  aws s3api put-public-access-block \
    --bucket "${BUCKET}" \
    --public-access-block-configuration \
      "BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true"

  # Enable versioning (protect state files)
  aws s3api put-bucket-versioning \
    --bucket "${BUCKET}" \
    --versioning-configuration Status=Enabled

  # Server-side encryption
  aws s3api put-bucket-encryption \
    --bucket "${BUCKET}" \
    --server-side-encryption-configuration '{
      "Rules": [{
        "ApplyServerSideEncryptionByDefault": {
          "SSEAlgorithm": "AES256"
        },
        "BucketKeyEnabled": true
      }]
    }'

  echo "  ✓ State bucket created"
fi

# ── DynamoDB Lock Table ───────────────────────────────────────────

echo "Creating DynamoDB lock table..."
if aws dynamodb describe-table --table-name "${TABLE}" --region "${REGION}" 2>/dev/null; then
  echo "  Table ${TABLE} already exists — skipping"
else
  aws dynamodb create-table \
    --table-name "${TABLE}" \
    --attribute-definitions AttributeName=LockID,AttributeType=S \
    --key-schema AttributeName=LockID,KeyType=HASH \
    --billing-mode PAY_PER_REQUEST \
    --region "${REGION}"

  aws dynamodb wait table-exists \
    --table-name "${TABLE}" \
    --region "${REGION}"

  echo "  ✓ Lock table created"
fi

echo ""
echo "=== Bootstrap complete ==="
echo ""
echo "Next steps:"
echo "  cd infrastructure/terraform/environments/${ENVIRONMENT}"
echo "  terraform init"
echo "  terraform plan -var-file=terraform.tfvars"
echo "  terraform apply -var-file=terraform.tfvars"
