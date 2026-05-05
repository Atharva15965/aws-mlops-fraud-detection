terraform {
  required_version = ">= 1.5"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }

  # Remote state in S3 (we'll create this bucket manually first)
  backend "s3" {
    bucket = "REPLACE_WITH_TFSTATE_BUCKET"
    key    = "fraud-mlops/terraform.tfstate"
    region = "ap-south-1"
  }
}

provider "aws" {
  region = var.aws_region
}

variable "aws_region" {
  type    = string
  default = "ap-south-1"
}

variable "project_name" {
  type    = string
  default = "mlops-fraud-detection"
}