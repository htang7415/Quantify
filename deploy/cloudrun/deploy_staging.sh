#!/usr/bin/env bash
# Deploy a digest-pinned, private Cloud Run staging revision.
set -euo pipefail

if [[ "${QUANTIFY_AUTHORIZE_STAGING_DEPLOY:-}" != "1" ]]; then
  echo "Refusing to deploy; set QUANTIFY_AUTHORIZE_STAGING_DEPLOY=1." >&2
  exit 2
fi

for required in GCP_PROJECT_ID GCP_REGION SERVICE_NAME RUNTIME_SERVICE_ACCOUNT \
  GEMINI_SECRET_NAME GEMINI_SECRET_VERSION IMAGE_DIGEST_REF STAGING_TAG STAGING_INVOKER_MEMBER; do
  : "${!required:?set $required}"
done
case "$GEMINI_SECRET_VERSION" in
  *[!0-9]*|'') echo "GEMINI_SECRET_VERSION must be a numbered version." >&2; exit 2 ;;
esac
if ! [[ "$IMAGE_DIGEST_REF" =~ @sha256:[0-9a-f]{64}$ ]]; then
  echo "IMAGE_DIGEST_REF must be an immutable @sha256 reference." >&2
  exit 2
fi
case "$STAGING_TAG" in
  candidate-*) ;;
  *) echo "STAGING_TAG must begin with candidate-." >&2; exit 2 ;;
esac
gcloud_bin="${GCLOUD_BIN:-gcloud}"
if ! command -v "$gcloud_bin" >/dev/null 2>&1; then
  echo "gcloud is unavailable; set GCLOUD_BIN to its executable path." >&2
  exit 2
fi

image_digest="${IMAGE_DIGEST_REF##*@}"
deploy_revision() {
  "$gcloud_bin" run deploy "$SERVICE_NAME" \
    --project="$GCP_PROJECT_ID" --region="$GCP_REGION" \
    --image="$IMAGE_DIGEST_REF" --tag="$STAGING_TAG" "$@" \
    --service-account="$RUNTIME_SERVICE_ACCOUNT" \
    --set-secrets="GEMINI_API_KEY=${GEMINI_SECRET_NAME}:${GEMINI_SECRET_VERSION}" \
    --set-env-vars="QUANTIFY_IMAGE_DIGEST=$image_digest" \
    --no-allow-unauthenticated --ingress=all \
    --min-instances=0 --max-instances=2 --concurrency=1 \
    --cpu=1 --memory=512Mi --port=8080 --timeout=10s
}
if "$gcloud_bin" run services describe "$SERVICE_NAME" \
  --project="$GCP_PROJECT_ID" --region="$GCP_REGION" >/dev/null 2>&1; then
  # Candidate revisions of an existing private staging service begin at zero
  # traffic and are reached through their tag only after smoke approval.
  deploy_revision --no-traffic
else
  # Cloud Run cannot create a service with zero traffic. This first revision is
  # still private IAM-only staging, with no production service or public route.
  echo "Creating the first IAM-private staging service revision." >&2
  deploy_revision
fi
"$gcloud_bin" run services add-iam-policy-binding "$SERVICE_NAME" \
  --project="$GCP_PROJECT_ID" --region="$GCP_REGION" \
  --member="$STAGING_INVOKER_MEMBER" --role="roles/run.invoker"
