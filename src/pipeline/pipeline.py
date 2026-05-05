"""Define and run the SageMaker Pipeline for credit card fraud detection.

DAG: Preprocess -> Train (XGBoost) -> Evaluate -> Conditional Register
"""
import os
from pathlib import Path

import boto3
import sagemaker
from dotenv import load_dotenv
from sagemaker.estimator import Estimator
from sagemaker.image_uris import retrieve as retrieve_image_uri
from sagemaker.inputs import TrainingInput
from sagemaker.processing import ProcessingInput, ProcessingOutput
from sagemaker.sklearn.processing import SKLearnProcessor
from sagemaker.workflow.condition_step import ConditionStep
from sagemaker.workflow.conditions import ConditionGreaterThanOrEqualTo
from sagemaker.workflow.functions import JsonGet
from sagemaker.workflow.parameters import ParameterFloat, ParameterString
from sagemaker.workflow.pipeline import Pipeline
from sagemaker.workflow.pipeline_context import PipelineSession
from sagemaker.workflow.properties import PropertyFile
from sagemaker.workflow.step_collections import RegisterModel
from sagemaker.workflow.steps import ProcessingStep, TrainingStep

load_dotenv(Path(__file__).resolve().parents[2] / ".env")

PROJECT_BUCKET = os.environ["PROJECT_BUCKET"]
AWS_REGION = os.environ.get("AWS_REGION", "ap-south-1")
SAGEMAKER_ROLE_ARN = os.environ["SAGEMAKER_ROLE_ARN"]

PIPELINE_NAME = "creditcard-fraud-pipeline"
MODEL_PACKAGE_GROUP_NAME = "creditcard-fraud-model-group"

PROCESSED_DATA_S3 = f"s3://{PROJECT_BUCKET}/processed/creditcard/"
PIPELINE_OUTPUTS_S3 = f"s3://{PROJECT_BUCKET}/pipeline-outputs/"

boto_session = boto3.Session(region_name=AWS_REGION)
pipeline_session = PipelineSession(
    boto_session=boto_session, default_bucket=PROJECT_BUCKET
)


def build_pipeline() -> Pipeline:
    # ---- Pipeline parameters (overridable at runtime) ----
    instance_type_processing = ParameterString(
        name="ProcessingInstanceType", default_value="ml.t3.medium"
    )
    instance_type_training = ParameterString(
        name="TrainingInstanceType", default_value="ml.m5.large"
    )
    pr_auc_threshold = ParameterFloat(name="PrAucThreshold", default_value=0.7)
    model_approval_status = ParameterString(
        name="ModelApprovalStatus", default_value="PendingManualApproval"
    )

    # ---- Step 1: Preprocess ----
    sklearn_processor = SKLearnProcessor(
        framework_version="1.2-1",
        instance_type=instance_type_processing,
        instance_count=1,
        role=SAGEMAKER_ROLE_ARN,
        sagemaker_session=pipeline_session,
        base_job_name="fraud-preprocess",
    )
    preprocess_step = ProcessingStep(
        name="Preprocess",
        processor=sklearn_processor,
        inputs=[
            ProcessingInput(
                source=PROCESSED_DATA_S3,
                destination="/opt/ml/processing/input",
                s3_data_distribution_type="ShardedByS3Key",
            )
        ],
        outputs=[
            ProcessingOutput(output_name="train", source="/opt/ml/processing/train"),
            ProcessingOutput(
                output_name="validation", source="/opt/ml/processing/validation"
            ),
            ProcessingOutput(output_name="test", source="/opt/ml/processing/test"),
        ],
        code="src/pipeline/preprocess.py",
    )

    # ---- Step 2: Train (built-in XGBoost) ----
    xgb_image_uri = retrieve_image_uri("xgboost", region=AWS_REGION, version="1.7-1")
    xgb_estimator = Estimator(
        image_uri=xgb_image_uri,
        instance_type=instance_type_training,
        instance_count=1,
        role=SAGEMAKER_ROLE_ARN,
        sagemaker_session=pipeline_session,
        output_path=f"{PIPELINE_OUTPUTS_S3}models/",
        base_job_name="fraud-xgb-train",
    )
    # Hyperparameters: scale_pos_weight handles class imbalance
    xgb_estimator.set_hyperparameters(
        objective="binary:logistic",
        eval_metric="aucpr",
        num_round=200,
        max_depth=6,
        eta=0.1,
        subsample=0.8,
        colsample_bytree=0.8,
        scale_pos_weight=577,  # ~ negative_count / positive_count
        verbosity=1,
    )
    train_step = TrainingStep(
        name="Train",
        estimator=xgb_estimator,
        inputs={
            "train": TrainingInput(
                s3_data=preprocess_step.properties.ProcessingOutputConfig.Outputs[
                    "train"
                ].S3Output.S3Uri,
                content_type="text/csv",
            ),
            "validation": TrainingInput(
                s3_data=preprocess_step.properties.ProcessingOutputConfig.Outputs[
                    "validation"
                ].S3Output.S3Uri,
                content_type="text/csv",
            ),
        },
    )

    # ---- Step 3: Evaluate ----
    eval_processor = SKLearnProcessor(
        framework_version="1.2-1",
        instance_type=instance_type_processing,
        instance_count=1,
        role=SAGEMAKER_ROLE_ARN,
        sagemaker_session=pipeline_session,
        base_job_name="fraud-evaluate",
    )
    evaluation_report = PropertyFile(
        name="EvaluationReport",
        output_name="evaluation",
        path="evaluation.json",
    )
    evaluate_step = ProcessingStep(
        name="Evaluate",
        processor=eval_processor,
        inputs=[
            ProcessingInput(
                source=train_step.properties.ModelArtifacts.S3ModelArtifacts,
                destination="/opt/ml/processing/model",
            ),
            ProcessingInput(
                source=preprocess_step.properties.ProcessingOutputConfig.Outputs[
                    "test"
                ].S3Output.S3Uri,
                destination="/opt/ml/processing/test",
            ),
        ],
        outputs=[
            ProcessingOutput(
                output_name="evaluation", source="/opt/ml/processing/evaluation"
            )
        ],
        code="src/pipeline/evaluate.py",
        property_files=[evaluation_report],
    )

    # ---- Step 4: Conditional Register Model ----
    register_step = RegisterModel(
        name="RegisterModel",
        estimator=xgb_estimator,
        model_data=train_step.properties.ModelArtifacts.S3ModelArtifacts,
        content_types=["text/csv"],
        response_types=["text/csv"],
        inference_instances=["ml.m5.large"],
        transform_instances=["ml.m5.large"],
        model_package_group_name=MODEL_PACKAGE_GROUP_NAME,
        approval_status=model_approval_status,
    )
    cond_pr_auc = ConditionGreaterThanOrEqualTo(
        left=JsonGet(
            step_name=evaluate_step.name,
            property_file=evaluation_report,
            json_path="metrics.pr_auc.value",
        ),
        right=pr_auc_threshold,
    )
    condition_step = ConditionStep(
        name="CheckPrAuc",
        conditions=[cond_pr_auc],
        if_steps=[register_step],
        else_steps=[],
    )

    pipeline = Pipeline(
        name=PIPELINE_NAME,
        parameters=[
            instance_type_processing,
            instance_type_training,
            pr_auc_threshold,
            model_approval_status,
        ],
        steps=[preprocess_step, train_step, evaluate_step, condition_step],
        sagemaker_session=pipeline_session,
    )
    return pipeline


def main():
    pipeline = build_pipeline()

    print(f"Upserting pipeline '{PIPELINE_NAME}'...")
    pipeline.upsert(role_arn=SAGEMAKER_ROLE_ARN)

    print("Starting pipeline execution...")
    execution = pipeline.start()
    print(f"Execution ARN: {execution.arn}")
    print(
        "Streaming execution status (Ctrl+C to stop watching, pipeline keeps running)..."
    )
    try:
        execution.wait()
        print("Pipeline finished.")
        print("Step statuses:")
        for step in execution.list_steps():
            print(f"  {step['StepName']:20s}  {step['StepStatus']}")
    except KeyboardInterrupt:
        print("Stopped watching. Pipeline still running in AWS — check Studio Console.")


if __name__ == "__main__":
    main()
