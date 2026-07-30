#!/usr/bin/env bash
# Build and push one immutable AWS Lambda image; this script never deploys it.
set -euo pipefail

if [[ "${QUANTIFY_AUTHORIZE_AWS_IMAGE_BUILD:-}" != "1" ]]; then
  echo "Refusing AWS image build; set QUANTIFY_AUTHORIZE_AWS_IMAGE_BUILD=1." >&2
  exit 2
fi
for required in AWS_REGION ECR_REPOSITORY IMAGE_TAG; do
  : "${!required:?set $required}"
done
[[ "$IMAGE_TAG" != "latest" ]] || {
  echo "IMAGE_TAG must not be latest." >&2
  exit 2
}
aws_bin="${AWS_BIN:-aws}"
command -v "$aws_bin" >/dev/null 2>&1 || {
  echo "aws is unavailable; set AWS_BIN to its executable path." >&2
  exit 2
}
command -v docker >/dev/null 2>&1 || {
  echo "docker is unavailable." >&2
  exit 2
}

account_id="$("$aws_bin" sts get-caller-identity --query Account --output text)"
repository_uri="$account_id.dkr.ecr.$AWS_REGION.amazonaws.com/$ECR_REPOSITORY"
"$aws_bin" ecr get-login-password --region="$AWS_REGION" | \
  docker login --username AWS --password-stdin "$account_id.dkr.ecr.$AWS_REGION.amazonaws.com"
docker buildx build --platform linux/amd64 --provenance=false --load \
  --file Dockerfile.lambda --tag "$repository_uri:$IMAGE_TAG" .
docker push "$repository_uri:$IMAGE_TAG"
digest="$("$aws_bin" ecr describe-images --region="$AWS_REGION" \
  --repository-name="$ECR_REPOSITORY" --image-ids imageTag="$IMAGE_TAG" \
  --query 'imageDetails[0].imageDigest' --output text)"
[[ "$digest" =~ ^sha256:[0-9a-f]{64}$ ]] || {
  echo "ECR did not return an immutable image digest." >&2
  exit 1
}
printf 'IMAGE_URI=%s@%s\nIMAGE_DIGEST=%s\n' "$repository_uri" "$digest" "$digest"
