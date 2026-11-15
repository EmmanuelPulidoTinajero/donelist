#!/usr/bin/env bash
# Runs on the EC2 instance, driven by .github/workflows/deploy.yml.
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
VERSION_URL="${VERSION_URL:-http://127.0.0.1:3000/version}"

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
python3 -m zipfile -e "$workdir/release.zip" "$workdir/out"

release_dir="$(find "$workdir/out" -mindepth 1 -maxdepth 1 -type d | head -n 1)"
if [ -z "$release_dir" ] || [ ! -f "$release_dir/package.json" ]; then
  echo "The release archive does not contain the application" >&2
  exit 1
fi

echo "Installing the release over $APP_DIR"
mkdir -p "$APP_DIR"
cp -a "$release_dir"/. "$APP_DIR"/
(cd "$APP_DIR" && npm ci --omit=dev --no-audit --no-fund)

echo "Recording APP_VERSION=$TAG in $ENV_FILE"
if sudo grep -q '^APP_VERSION=' "$ENV_FILE"; then
  sudo sed -i "s|^APP_VERSION=.*|APP_VERSION=${TAG}|" "$ENV_FILE"
else
  echo "APP_VERSION=${TAG}" | sudo tee -a "$ENV_FILE" > /dev/null
fi

echo "Restarting $SERVICE_UNIT"
sudo systemctl restart "$SERVICE_UNIT"

served_version() {
  curl --fail --silent --show-error "$VERSION_URL" 2>/dev/null |
    python3 -c 'import json,sys; print(json.load(sys.stdin).get("version", ""))' 2>/dev/null ||
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
