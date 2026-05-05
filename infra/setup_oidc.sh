#!/usr/bin/env bash
# One-time setup: create the GitHub OIDC provider in AWS and an IAM role
# that GitHub Actions can assume.
set -euo pipefail

# REPLACE with your GitHub username/org and repo name
GITHUB_OWNER="Atharva15965"
GITHUB_REPO="aws-mlops-fraud-detection"

ROLE_NAME="MLOpsGitHubActionsRole"
THUMBPRINT="6938fd4d98bab03faadb97b34396831e3780aea1"  # GitHub's well-known OIDC thumbprint

ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
PROVIDER_ARN="arn:aws:iam::${ACCOUNT_ID}:oidc-provider/token.actions.githubusercontent.com"

# 1. Create the OIDC provider (skip if it already exists)
if ! aws iam get-open-id-connect-provider --open-id-connect-provider-arn "$PROVIDER_ARN" >/dev/null 2>&1; then
  aws iam create-open-id-connect-provider \
    --url https://token.actions.githubusercontent.com \
    --client-id-list sts.amazonaws.com \
    --thumbprint-list "$THUMBPRINT"
  echo "Created OIDC provider"
else
  echo "OIDC provider already exists"
fi

# 2. Trust policy: allow GH Actions in this repo to assume the role
TRUST_POLICY=$(cat <<EOF
{
  "Version": "2012-10-17",
  "Statement": [{
    "Effect": "Allow",
    "Principal": {"Federated": "$PROVIDER_ARN"},
    "Action": "sts:AssumeRoleWithWebIdentity",
    "Condition": {
      "StringEquals": {"token.actions.githubusercontent.com:aud": "sts.amazonaws.com"},
      "StringLike": {"token.actions.githubusercontent.com:sub": "repo:${GITHUB_OWNER}/${GITHUB_REPO}:*"}
    }
  }]
}
EOF
)

# 3. Create the role
if ! aws iam get-role --role-name "$ROLE_NAME" >/dev/null 2>&1; then
  aws iam create-role --role-name "$ROLE_NAME" --assume-role-policy-document "$TRUST_POLICY"
  echo "Created role: $ROLE_NAME"
else
  aws iam update-assume-role-policy --role-name "$ROLE_NAME" --policy-document "$TRUST_POLICY"
  echo "Updated trust policy on existing role"
fi

# 4. Attach broad permissions (we'll narrow these later)
aws iam attach-role-policy --role-name "$ROLE_NAME" --policy-arn arn:aws:iam::aws:policy/AmazonS3FullAccess
aws iam attach-role-policy --role-name "$ROLE_NAME" --policy-arn arn:aws:iam::aws:policy/AmazonSageMakerFullAccess
aws iam attach-role-policy --role-name "$ROLE_NAME" --policy-arn arn:aws:iam::aws:policy/IAMFullAccess
aws iam attach-role-policy --role-name "$ROLE_NAME" --policy-arn arn:aws:iam::aws:policy/AWSLambda_FullAccess
aws iam attach-role-policy --role-name "$ROLE_NAME" --policy-arn arn:aws:iam::aws:policy/AmazonAPIGatewayAdministrator

echo ""
echo "============================================"
echo "ROLE_ARN=arn:aws:iam::${ACCOUNT_ID}:role/${ROLE_NAME}"
echo "============================================"
echo "Add this to GitHub Actions secrets/variables (we'll do that next)."