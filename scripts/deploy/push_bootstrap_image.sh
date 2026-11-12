#!/usr/bin/env bash
# First deploy only: push an image tagged "bootstrap" so the ECS service has
# something to run before CI's first deploy. After that CI pushes commit SHAs.
#
#   terraform -chdir=infra/terraform apply -target=aws_ecr_repository.app
#   scripts/deploy/push_bootstrap_image.sh
#   terraform -chdir=infra/terraform apply
set -euo pipefail

cd "$(dirname "$0")/../.."
repo_url="$(terraform -chdir=infra/terraform output -raw ecr_repository_url)"
registry="${repo_url%%/*}"
region="$(echo "$registry" | cut -d. -f4)"

if aws ecr describe-images --region "$region" --repository-name splitkit \
     --image-ids imageTag=bootstrap >/dev/null 2>&1; then
  echo "bootstrap image already in ECR; nothing to do"
  exit 0
fi

aws ecr get-login-password --region "$region" | docker login --username AWS --password-stdin "$registry"
# Fargate runs X86_64; build for it even on Apple Silicon.
docker buildx build --platform linux/amd64 -f infra/Dockerfile -t "$repo_url:bootstrap" --push .
echo "pushed $repo_url:bootstrap"
