#!/bin/bash
# scripts/localstack-init.sh
# Runs inside LocalStack on first boot to create required S3 buckets.
# Mirrors the production bucket structure.

set -e

echo "=== NoteFlow LocalStack Init ==="

AWS_CMD="aws --endpoint-url=http://localhost:4566 --region us-east-1"

# ── Create S3 buckets ─────────────────────────────────────────────

echo "Creating S3 buckets..."

$AWS_CMD s3 mb s3://noteflow-attachments-local 2>/dev/null || true
$AWS_CMD s3 mb s3://noteflow-exports-local     2>/dev/null || true

# Enable versioning on attachments bucket (mirrors prod)
$AWS_CMD s3api put-bucket-versioning \
  --bucket noteflow-attachments-local \
  --versioning-configuration Status=Enabled

# CORS for attachments bucket (allows direct browser uploads)
$AWS_CMD s3api put-bucket-cors \
  --bucket noteflow-attachments-local \
  --cors-configuration '{
    "CORSRules": [{
      "AllowedOrigins": ["*"],
      "AllowedMethods": ["GET","PUT","POST","HEAD","DELETE"],
      "AllowedHeaders": ["*"],
      "ExposeHeaders":  ["ETag"],
      "MaxAgeSeconds":  3600
    }]
  }'

# Lifecycle: auto-expire exports after 7 days
$AWS_CMD s3api put-bucket-lifecycle-configuration \
  --bucket noteflow-exports-local \
  --lifecycle-configuration '{
    "Rules": [{
      "ID":     "expire-exports",
      "Status": "Enabled",
      "Expiration": { "Days": 7 },
      "Filter": { "Prefix": "" }
    }]
  }'

echo "✓ S3 buckets ready:"
$AWS_CMD s3 ls

echo "=== LocalStack init complete ==="
