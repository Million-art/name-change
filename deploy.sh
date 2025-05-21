#!/bin/bash

# AWS Configuration
AWS_REGION="us-east-1"  # Change this to your preferred region
ECR_REPOSITORY="name-change-bot"
ECR_IMAGE_TAG="latest"

# Build the Docker image
echo "Building Docker image..."
docker build -t $ECR_REPOSITORY:$ECR_IMAGE_TAG .

# Login to Amazon ECR
echo "Logging in to Amazon ECR..."
aws ecr get-login-password --region $AWS_REGION | docker login --username AWS --password-stdin $(aws sts get-caller-identity --query Account --output text).dkr.ecr.$AWS_REGION.amazonaws.com

# Create ECR repository if it doesn't exist
aws ecr describe-repositories --repository-names $ECR_REPOSITORY --region $AWS_REGION || \
    aws ecr create-repository --repository-name $ECR_REPOSITORY --region $AWS_REGION

# Tag the image for ECR
ECR_REPOSITORY_URI=$(aws ecr describe-repositories --repository-names $ECR_REPOSITORY --region $AWS_REGION --query 'repositories[0].repositoryUri' --output text)
docker tag $ECR_REPOSITORY:$ECR_IMAGE_TAG $ECR_REPOSITORY_URI:$ECR_IMAGE_TAG

# Push the image to ECR
echo "Pushing image to ECR..."
docker push $ECR_REPOSITORY_URI:$ECR_IMAGE_TAG

# Update ECS service (if using ECS)
echo "Updating ECS service..."
aws ecs update-service --cluster name-change-bot-cluster --service name-change-bot-service --force-new-deployment --region $AWS_REGION

echo "Deployment completed!" 