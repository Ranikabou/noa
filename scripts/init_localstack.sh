#!/bin/bash
# Create S3 bucket in LocalStack. Run after: docker compose up -d
# Usage: ./scripts/init_localstack.sh

set -e
BUCKET="${S3_BUCKET_ASSETS:-noa-assets}"
echo "Creating bucket: $BUCKET"
awslocal s3 mb "s3://$BUCKET" 2>/dev/null || awslocal s3 ls "s3://$BUCKET" >/dev/null 2>&1 && echo "Bucket exists" || true
