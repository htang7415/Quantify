#!/usr/bin/env bash
# Create prerequisite GCP resources only after a deliberate authorization step.
set -euo pipefail

if [[ "${QUANTIFY_AUTHORIZE_GCP_BOOTSTRAP:-}" != "1" ]]; then
  echo "Refusing to create cloud resources; set QUANTIFY_AUTHORIZE_GCP_BOOTSTRAP=1." >&2
  exit 2
fi

: "${GCP_PROJECT_ID:?set GCP_PROJECT_ID}"
: "${GCP_REGION:?set GCP_REGION}"
: "${ARTIFACT_REPOSITORY:?set ARTIFACT_REPOSITORY}"
: "${RUNTIME_SERVICE_ACCOUNT:?set RUNTIME_SERVICE_ACCOUNT}"
: "${GEMINI_SECRET_NAME:?set GEMINI_SECRET_NAME}"
gcloud_bin="${GCLOUD_BIN:-gcloud}"
if ! command -v "$gcloud_bin" >/dev/null 2>&1; then
  echo "gcloud is unavailable; set GCLOUD_BIN to its executable path." >&2
  exit 2
fi

service_account_name="${RUNTIME_SERVICE_ACCOUNT%@*}"
"$gcloud_bin" artifacts repositories describe "$ARTIFACT_REPOSITORY" \
  --project="$GCP_PROJECT_ID" --location="$GCP_REGION" >/dev/null 2>&1 \
  || "$gcloud_bin" artifacts repositories create "$ARTIFACT_REPOSITORY" \
    --project="$GCP_PROJECT_ID" --location="$GCP_REGION" \
    --repository-format=docker --description="Quantify immutable API images"
"$gcloud_bin" iam service-accounts describe "$RUNTIME_SERVICE_ACCOUNT" \
  --project="$GCP_PROJECT_ID" >/dev/null 2>&1 \
  || "$gcloud_bin" iam service-accounts create "$service_account_name" \
    --project="$GCP_PROJECT_ID" --display-name="Quantify Core runtime"
"$gcloud_bin" secrets add-iam-policy-binding "$GEMINI_SECRET_NAME" \
  --project="$GCP_PROJECT_ID" \
  --member="serviceAccount:$RUNTIME_SERVICE_ACCOUNT" \
  --role="roles/secretmanager.secretAccessor"
