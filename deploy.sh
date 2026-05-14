#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BUILD_DIR="${BUILD_DIR:-/tmp/portfolio-deploy}"
ZIP_PATH="${ZIP_PATH:-/tmp/portfolio-deploy.zip}"
FUNCTION_NAME="${FUNCTION_NAME:-Portfolio}"
AWS_REGION="${AWS_REGION:-us-west-2}"
PYTHON_BIN="${PYTHON_BIN:-$ROOT_DIR/.venv/bin/python}"

if [[ ! -x "$PYTHON_BIN" ]]; then
  echo "Python executable not found at $PYTHON_BIN" >&2
  exit 1
fi

rm -rf "$BUILD_DIR" "$ZIP_PATH"
mkdir -p "$BUILD_DIR"

"$PYTHON_BIN" -m pip install -q -r "$ROOT_DIR/requirements.txt" -t "$BUILD_DIR"

cp "$ROOT_DIR/app.py" "$ROOT_DIR/config.py" "$ROOT_DIR/notifications.py" "$ROOT_DIR/requirements.txt" "$BUILD_DIR/"
cp -R "$ROOT_DIR/assets" "$ROOT_DIR/templates" "$BUILD_DIR/"

# These local source videos are not used by the live app and inflate the Lambda zip.
rm -f "$BUILD_DIR/assets/GYM_hero.mp4" "$BUILD_DIR/assets/workout.mp4" "$BUILD_DIR/assets/workout-web.mp4" "$BUILD_DIR/assets/workout-web-10s.mp4"

(
  cd "$BUILD_DIR"
  zip -qr "$ZIP_PATH" .
)

aws lambda update-function-code \
  --function-name "$FUNCTION_NAME" \
  --region "$AWS_REGION" \
  --zip-file "fileb://$ZIP_PATH"

aws lambda wait function-updated \
  --function-name "$FUNCTION_NAME" \
  --region "$AWS_REGION"

aws lambda get-function-configuration \
  --function-name "$FUNCTION_NAME" \
  --region "$AWS_REGION" \
  --query '{LastUpdateStatus:LastUpdateStatus,CodeSha256:CodeSha256}'