# IAM role for SageMaker (mirrors what we created manually in Phase 2C)
resource "aws_iam_role" "sagemaker" {
  name = "MLOpsSageMakerRoleTF"  # different name so we don't conflict with the manually created one
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "sagemaker.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role_policy_attachment" "sagemaker_full" {
  role       = aws_iam_role.sagemaker.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonSageMakerFullAccess"
}

resource "aws_iam_role_policy_attachment" "sagemaker_s3" {
  role       = aws_iam_role.sagemaker.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonS3FullAccess"
}

output "sagemaker_role_arn" {
  value = aws_iam_role.sagemaker.arn
}