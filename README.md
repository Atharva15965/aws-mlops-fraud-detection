# AWS MLOps Fraud Detection

End-to-end MLOps system on AWS that detects credit card fraud, retrains itself automatically when data drift is detected, deploys via serverless inference behind a public API, and ships every change through GitHub Actions CI/CD. 


## Architecture

```mermaid
flowchart TD
    GH[GitHub Repo]
    GA[GitHub Actions: OIDC + CI/CD]
    GH --> GA

    GA --> AWS[AWS Cloud]

    AWS --> S3[S3 raw zone<br/>Hive partitioned]
    S3 --> GC[Glue Catalog<br/>+ Athena]
    S3 --> FS[SageMaker Feature Store<br/>online + offline]

    GC --> SP[SageMaker Pipeline]
    FS --> SP
    SP --> P1[Preprocess]
    P1 --> P2[Train XGBoost]
    P2 --> P3[Evaluate]
    P3 --> MR[Model Registry<br/>Pending → Approved]
    MR --> EP[Serverless Endpoint]

    Client[Client app/curl] --> AG[API Gateway]
    AG --> LP[Lambda Predict]
    LP --> EP
    LP --> DC[S3 Data Capture]

    DC --> DD[Drift Detector Lambda<br/>hourly EventBridge]
    DD --> CW[CloudWatch Alarm]
    CW --> SNS[SNS Topic]
    SNS --> Email[Email Alert]
    SNS --> RL[Retrain Lambda]
    RL --> SP

    style GH fill:#222,color:#fff
    style GA fill:#222,color:#fff
    style AWS fill:#FF9900,color:#000
    style S3 fill:#3B48CC,color:#fff
    style GC fill:#3B48CC,color:#fff
    style FS fill:#3B48CC,color:#fff
    style SP fill:#01A88D,color:#fff
    style P1 fill:#01A88D,color:#fff
    style P2 fill:#01A88D,color:#fff
    style P3 fill:#01A88D,color:#fff
    style MR fill:#01A88D,color:#fff
    style EP fill:#01A88D,color:#fff
    style Client fill:#444,color:#fff
    style AG fill:#9D5025,color:#fff
    style LP fill:#9D5025,color:#fff
    style DC fill:#3B48CC,color:#fff
    style DD fill:#C7131F,color:#fff
    style CW fill:#C7131F,color:#fff
    style SNS fill:#C7131F,color:#fff
    style Email fill:#444,color:#fff
    style RL fill:#C7131F,color:#fff
```

## Tech Stack

- **Cloud**: AWS (S3, Glue, Athena, SageMaker, Lambda, API Gateway, EventBridge, SNS, CloudWatch, IAM)
- **ML**: XGBoost, scikit-learn, pandas
- **MLOps**: SageMaker Pipelines, Feature Store, Model Registry, Custom Drift Detection
- **DevOps**: GitHub Actions (OIDC), Terraform, Python 3.11
- **Region**: ap-south-1 (Mumbai)

## Key Metrics

Trained on the [Kaggle Credit Card Fraud Dataset](https://www.kaggle.com/datasets/mlg-ulb/creditcardfraud) — 284,807 transactions, 0.17% fraud rate.

| Metric | Test Set Value |
|---|---|
| PR-AUC (primary) | ~0.85 |
| ROC-AUC | ~0.97 |
| Fraud detected | high recall + balanced precision |

## Repository Structure

```
.
├── .github/workflows/      # CI + Deploy via GitHub Actions OIDC
├── infra/                  # IAM trust policies, OIDC setup, Terraform skeleton
├── notebooks/              # EDA notebook + findings.md
├── src/
│   ├── data/               # Ingest + feature engineering
│   ├── feature_store/      # Feature Group creation + ingest
│   ├── pipeline/           # SageMaker Pipeline + local fallback + manual register
│   ├── inference/          # Approve, serverless endpoint, Lambda handler, deploy API
│   └── monitoring/         # Drift detector, baseline, alerts, retrain Lambda
├── tests/                  # Pytest smoke tests
├── teardown.sh             # One-command cleanup
└── requirements.txt
```

## Phases Built

- **Phase 0** — Account hardening and aws limitations scoping, IAM, repo skeleton
- **Phase 1** — Data lake (S3 + Glue + Athena) with Hive partitioning
- **Phase 2** — EDA + Feature engineering (Parquet) + SageMaker Feature Store
- **Phase 3** — Training pipeline: SageMaker Pipelines DAG (preprocess → train → evaluate → register)
- **Phase 4** — Model approval + serverless deployment
- **Phase 5** — Public API: Lambda + API Gateway with API key auth
- **Phase 6** — Custom drift detection + alerting + auto-retrain wiring
- **Phase 7** — CI/CD: GitHub Actions OIDC + Terraform skeleton

## Quick Start

```bash
git clone https://github.com/Atharva15965/aws-mlops-fraud-detection.git
cd aws-mlops-fraud-detection
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env  # edit with your bucket, region, role ARNs
```

### Test the public API
```bash
curl -X POST 'YOUR_API_URL' \
  -H 'x-api-key: YOUR_API_KEY' \
  -H 'Content-Type: application/json' \
  -d '{"features": [...34 floats...]}'
# → {"fraud_probability": 0.987, "is_fraud": true, "variant": "VariantA", "capture_id": "..."}
```

### Tear down everything
```bash
./teardown.sh
```

## Costs

Designed for AWS Free Tier:
- Serverless Inference: pay per invocation (~$0.0000008/call)
- Lambda + API Gateway: 1M req/month free
- S3 + Glue + Athena: pennies for this dataset
- SageMaker training: 50 free hours/month of `ml.m5.xlarge`

Total cost for a month of light use: under $5.

## Trade offs Worth Noting

- **Serverless Inference** instead of real-time endpoints — keeps idle costs at zero, but limits us to one variant per endpoint. A/B routing happens in the Lambda layer instead.
- **Custom drift detection** instead of SageMaker Model Monitor — Model Monitor's data capture isn't supported on serverless endpoints, so the Lambda writes captures to S3 directly and a scheduled Lambda computes drift scores.
- **Local training fallback** — pending instance quota during build; the SageMaker Pipeline is fully defined and registers v2 automatically once quota approves.

## License

MIT.
