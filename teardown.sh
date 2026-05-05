#!/usr/bin/env bash
# Teardown all AWS resources created during this project.
# Safe to run multiple times — uses `|| true` to ignore "already deleted" errors.
set +e

source .env

echo "=== Tearing down AWS resources ==="
echo "Bucket: $PROJECT_BUCKET"
echo "Region: $AWS_REGION"
echo ""
read -p "This will delete EVERYTHING. Type 'yes' to continue: " confirm
if [ "$confirm" != "yes" ]; then echo "Aborted."; exit 1; fi

# === SageMaker ===
echo "[SageMaker] Stopping monitoring schedule..."
aws sagemaker stop-monitoring-schedule --monitoring-schedule-name creditcard-fraud-drift-monitor 2>/dev/null || true
aws sagemaker delete-monitoring-schedule --monitoring-schedule-name creditcard-fraud-drift-monitor 2>/dev/null || true

echo "[SageMaker] Deleting endpoint..."
aws sagemaker delete-endpoint --endpoint-name creditcard-fraud-endpoint 2>/dev/null || true
aws sagemaker delete-endpoint-config --endpoint-config-name creditcard-fraud-endpoint-config 2>/dev/null || true
aws sagemaker delete-endpoint-config --endpoint-config-name creditcard-fraud-endpoint-config-v2 2>/dev/null || true
aws sagemaker delete-model --model-name creditcard-fraud-model-a 2>/dev/null || true
aws sagemaker delete-model --model-name creditcard-fraud-model-b 2>/dev/null || true

echo "[SageMaker] Deleting model packages + group..."
for arn in $(aws sagemaker list-model-packages --model-package-group-name creditcard-fraud-model-group --query 'ModelPackageSummaryList[*].ModelPackageArn' --output text 2>/dev/null); do
  aws sagemaker delete-model-package --model-package-name "$arn" 2>/dev/null || true
done
aws sagemaker delete-model-package-group --model-package-group-name creditcard-fraud-model-group 2>/dev/null || true

echo "[SageMaker] Deleting feature group..."
aws sagemaker delete-feature-group --feature-group-name creditcard-fraud-features 2>/dev/null || true

echo "[SageMaker] Deleting pipeline..."
aws sagemaker delete-pipeline --pipeline-name creditcard-fraud-pipeline 2>/dev/null || true

# === Lambda + API Gateway ===
echo "[Lambda] Deleting functions..."
for fn in creditcard-fraud-predict creditcard-fraud-drift-detector creditcard-fraud-retrain; do
  aws lambda delete-function --function-name "$fn" 2>/dev/null || true
done

echo "[API Gateway] Deleting API..."
API_ID=$(aws apigateway get-rest-apis --query 'items[?name==`creditcard-fraud-api`].id' --output text 2>/dev/null)
if [ -n "$API_ID" ] && [ "$API_ID" != "None" ]; then
  aws apigateway delete-rest-api --rest-api-id "$API_ID" 2>/dev/null || true
fi

# === EventBridge ===
echo "[EventBridge] Deleting rule..."
aws events remove-targets --rule creditcard-fraud-drift-schedule --ids 1 2>/dev/null || true
aws events delete-rule --name creditcard-fraud-drift-schedule 2>/dev/null || true

# === SNS ===
echo "[SNS] Deleting topic..."
TOPIC_ARN=$(aws sns list-topics --query 'Topics[?contains(TopicArn, `creditcard-fraud-drift-alerts`)].TopicArn' --output text 2>/dev/null)
if [ -n "$TOPIC_ARN" ] && [ "$TOPIC_ARN" != "None" ]; then
  aws sns delete-topic --topic-arn "$TOPIC_ARN" 2>/dev/null || true
fi

# === CloudWatch ===
echo "[CloudWatch] Deleting alarm..."
aws cloudwatch delete-alarms --alarm-names "creditcard-fraud-feature-drift" 2>/dev/null || true

# === Glue ===
echo "[Glue] Deleting database (cascades to tables)..."
aws glue delete-database --name mlops_fraud_detection 2>/dev/null || true
aws glue delete-crawler --name creditcard-raw-crawler 2>/dev/null || true

# === IAM Roles ===
echo "[IAM] Deleting roles..."
for role in MLOpsSageMakerRole MLOpsGlueCrawlerRole MLOpsFraudLambdaRole MLOpsFraudDriftRole MLOpsFraudRetrainRole MLOpsGitHubActionsRole; do
  # Detach managed policies
  for arn in $(aws iam list-attached-role-policies --role-name "$role" --query 'AttachedPolicies[*].PolicyArn' --output text 2>/dev/null); do
    aws iam detach-role-policy --role-name "$role" --policy-arn "$arn" 2>/dev/null || true
  done
  # Delete inline policies
  for name in $(aws iam list-role-policies --role-name "$role" --query 'PolicyNames' --output text 2>/dev/null); do
    aws iam delete-role-policy --role-name "$role" --policy-name "$name" 2>/dev/null || true
  done
  aws iam delete-role --role-name "$role" 2>/dev/null || true
done

# === S3 ===
echo "[S3] Emptying and deleting bucket..."
read -p "Delete S3 bucket $PROJECT_BUCKET? (y/n): " del
if [ "$del" = "y" ]; then
  aws s3 rb "s3://$PROJECT_BUCKET" --force 2>/dev/null || true
fi

# === OIDC Provider ===
echo "[IAM] Deleting OIDC provider..."
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
aws iam delete-open-id-connect-provider --open-id-connect-provider-arn "arn:aws:iam::${ACCOUNT_ID}:oidc-provider/token.actions.githubusercontent.com" 2>/dev/null || true

echo ""
echo "=== Teardown complete ==="
echo "Verify in the AWS Console that no rogue resources remain billing."


#chmod +x teardown.sh(command to run this file to delete all aws services created)