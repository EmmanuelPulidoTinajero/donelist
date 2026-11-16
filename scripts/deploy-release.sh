#!/usr/bin/env bash
# Runs on the EC2 instance, driven by .github/workflows/deploy.yml over SSM
# Run Command (no SSH, no port 22, no private key in a repository secret).
#
# Downloads the zip asset attached to a published GitHub release, installs it
# over the checkout that user_data created, records the release tag as
# APP_VERSION and restarts the service until /version reports the new tag.
#
# usage: deploy-release.sh <release-tag> <asset-url>
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/to-do-list-api}"
ENV_FILE="${ENV_FILE:-/etc/to-do-list-api.env}"
SERVICE_UNIT="${SERVICE_UNIT:-to-do-list-api}"
VERSION_URL="${VERSION_URL:-http://127.0.0.1:8000/version}"
PYTHON_BIN="${PYTHON_BIN:-$APP_DIR/.venv/bin/python}"

# SSM Run Command executes as root; a manual run may not.
if [ "$(id -u)" -eq 0 ]; then
  SUDO=""
else
  SUDO="sudo"
fi

if [ "$#" -ne 2 ]; then
  echo "usage: $0 <release-tag> <asset-url>" >&2
  exit 64
fi

TAG="$1"
ASSET_URL="$2"

case "$TAG" in
  v*.*.*) ;;
  *)
    echo "Unexpected release tag: $TAG" >&2
    exit 64
    ;;
esac

case "$ASSET_URL" in
  https://github.com/*/releases/download/*) ;;
  *)
    echo "Unexpected release asset URL: $ASSET_URL" >&2
    exit 64
    ;;
esac

workdir="$(mktemp -d)"
trap 'rm -rf "$workdir"' EXIT

echo "Downloading $ASSET_URL"
curl --fail --silent --show-error --location --retry 3 --retry-delay 5 \
  -o "$workdir/release.zip" "$ASSET_URL"

echo "Extracting the release archive"
"$PYTHON_BIN" -m zipfile -e "$workdir/release.zip" "$workdir/out"

release_dir="$(find "$workdir/out" -mindepth 1 -maxdepth 1 -type d | head -n 1)"
if [ -z "$release_dir" ] || [ ! -f "$release_dir/requirements.txt" ]; then
  echo "The release archive does not contain the application" >&2
  exit 1
fi

echo "Installing the release over $APP_DIR"
mkdir -p "$APP_DIR"
cp -a "$release_dir"/. "$APP_DIR"/
"$PYTHON_BIN" -m pip install --quiet -r "$APP_DIR/requirements.txt"
$SUDO chown -R "$(stat -c '%U' "$APP_DIR")": "$APP_DIR"

echo "Recording APP_VERSION=$TAG in $ENV_FILE"
if $SUDO grep -q '^APP_VERSION=' "$ENV_FILE"; then
  $SUDO sed -i "s|^APP_VERSION=.*|APP_VERSION=${TAG}|" "$ENV_FILE"
else
  echo "APP_VERSION=${TAG}" | $SUDO tee -a "$ENV_FILE" >/dev/null
fi

echo "Restarting $SERVICE_UNIT"
$SUDO systemctl restart "$SERVICE_UNIT"

served_version() {
  curl --fail --silent --show-error "$VERSION_URL" 2>/dev/null |
    "$PYTHON_BIN" -c 'import json,sys; print(json.load(sys.stdin).get("version", ""))' 2>/dev/null ||
    true
}

for attempt in $(seq 1 30); do
  served="$(served_version)"
  if [ "$served" = "$TAG" ]; then
    echo "The instance now serves version $served"
    exit 0
  fi
  echo "Attempt $attempt: the instance reports '${served:-no answer}', waiting for $TAG"
  sleep 2
done

echo "The service never reported version $TAG after the restart" >&2
exit 1
