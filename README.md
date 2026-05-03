# AWS MLOps Fraud Detection

End-to-end MLOps system on AWS for credit card fraud detection. Features automated retraining on data drift, A/B model deployment, and full CI/CD.

## Architecture
See `docs/architecture.md`.

## Local setup
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
aws configure
```

## Deploy
```bash
cd infra/envs/dev
terraform init && terraform apply
```

## Status
🚧 Under construction. See `PROJECT_PLAN.md` for phase progress.
