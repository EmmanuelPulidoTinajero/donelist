#!/usr/bin/env bash
#
# Refresh the repository secrets and variables the workflows in
# .github/workflows read.
#
# The AWS credentials are read from the standard AWS CLI profile and piped
# straight into `gh secret set`, so no access key, secret key or session token
# is ever printed, passed as a command-line argument, or written to the shell
# history.
#
# Usage:
#   scripts/set-github-config.sh                     # secrets and variables
#   scripts/set-github-config.sh http://1.2.3.4:8000 # ... and API_URL
#
# Run it once per Learner Lab session: the lab replaces the credentials and
# wipes the S3 state bucket every time it restarts.
set -euo pipefail

REPO="${REPO:-EmmanuelPulidoTinajero/donelist}"
PROJECT_NAME="${PROJECT_NAME:-to-do-list-api}"
AWS_REGION_NAME="${AWS_REGION_NAME:-us-east-1}"
ALERT_EMAIL="${ALERT_EMAIL:-jepulidotinajero@gmail.com}"
INSTANCE_PROFILE_NAME="${INSTANCE_PROFILE_NAME:-LabInstanceProfile}"
API_URL="${1:-}"

# gh installed by winget is not on the PATH of every shell, so fall back to the
# documented install location instead of failing with "command not found".
GH="$(command -v gh || true)"
if [ -z "$GH" ] && [ -x "/c/Program Files/GitHub CLI/gh.exe" ]; then
    GH="/c/Program Files/GitHub CLI/gh.exe"
fi
if [ -z "$GH" ]; then
    echo "gh was not found. Install it, then run 'gh auth login'." >&2
    exit 1
fi
command -v aws >/dev/null 2>&1 || { echo "aws was not found." >&2; exit 1; }

# The backend is created by hand, not by Terraform, and the lab deletes it on
# every reset. Setting TF_STATE_BUCKET to a bucket that does not exist makes
# `terraform init` fail later with a much less obvious message, so check first.
account="$(aws sts get-caller-identity --query Account --output text)"
bucket="to-do-list-api-tfstate-${account}"
if ! aws s3api head-bucket --bucket "$bucket" >/dev/null 2>&1; then
    cat >&2 <<EOF
The Terraform state bucket does not exist: $bucket

Recreate it before setting TF_STATE_BUCKET, or the next \`terraform init\`
fails. See "Create the Terraform state bucket" in README.md.
EOF
    exit 1
fi

set_secret() {
    local name="$1" key="$2" value
    # The trailing CR matters: a Windows credentials file keeps its values
    # clean, but `aws configure get` output through a pipe can carry one, and a
    # secret with a stray CR fails authentication in the runner.
    value="$(aws configure get "$key" 2>/dev/null | tr -d '\r' || true)"
    if [ "${#value}" -lt 8 ]; then
        echo "refusing to set $name: the AWS profile has no $key" >&2
        return 1
    fi
    printf '%s' "$value" | "$GH" secret set "$name" --repo "$REPO" >/dev/null
    echo "secret   $name"
}

set_variable() {
    "$GH" variable set "$1" --body "$2" --repo "$REPO" >/dev/null
    echo "variable $1 = $2"
}

set_secret AWS_ACCESS_KEY_ID aws_access_key_id
set_secret AWS_SECRET_ACCESS_KEY aws_secret_access_key
set_secret AWS_SESSION_TOKEN aws_session_token

set_variable TF_STATE_BUCKET "$bucket"
set_variable INSTANCE_PROFILE_NAME "$INSTANCE_PROFILE_NAME"
set_variable ALERT_EMAIL "$ALERT_EMAIL"
set_variable AWS_REGION "$AWS_REGION_NAME"
set_variable PROJECT_NAME "$PROJECT_NAME"

# API_URL follows the instance, so it can only be set after a successful apply.
if [ -z "$API_URL" ]; then
    echo "skipped  API_URL (pass it as the first argument after an apply)"
else
    set_variable API_URL "$API_URL"
fi
