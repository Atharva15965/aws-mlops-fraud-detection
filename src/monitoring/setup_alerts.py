"""Set up SNS topic and email subscription for drift alerts."""
import os
import sys
from pathlib import Path

import boto3
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[2] / ".env")
AWS_REGION = os.environ.get("AWS_REGION", "ap-south-1")

if len(sys.argv) < 2:
    print("Usage: python src/monitoring/setup_alerts.py <your_email@example.com>")
    sys.exit(1)
EMAIL = sys.argv[1]

sns = boto3.client("sns", region_name=AWS_REGION)
topic = sns.create_topic(Name="creditcard-fraud-drift-alerts")
TOPIC_ARN = topic["TopicArn"]
print(f"SNS topic: {TOPIC_ARN}")

sns.subscribe(TopicArn=TOPIC_ARN, Protocol="email", Endpoint=EMAIL)
print(f"Subscribed {EMAIL}. Check your inbox and CONFIRM the subscription email!")
print(f"\nSave this for the next step:")
print(f"  TOPIC_ARN={TOPIC_ARN}")
