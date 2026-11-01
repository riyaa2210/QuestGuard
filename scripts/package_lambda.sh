#!/bin/bash
# Packages the Lambda functions into a zip file for deployment.
# Run from the repo root: bash scripts/package_lambda.sh

set -e

BUILD_DIR="$(mktemp -d)"
ZIP_PATH="lambda/queueguard_lambda.zip"

echo "==> Installing Lambda dependencies into $BUILD_DIR ..."
pip install --quiet -r lambda/requirements.txt --target "$BUILD_DIR"

echo "==> Copying source files ..."
cp -r app "$BUILD_DIR/app"
cp -r lambda/*.py "$BUILD_DIR/"

echo "==> Creating $ZIP_PATH ..."
cd "$BUILD_DIR"
zip -r9 "$OLDPWD/$ZIP_PATH" . > /dev/null

cd "$OLDPWD"
rm -rf "$BUILD_DIR"

echo "==> Done. Lambda package: $ZIP_PATH ($(du -h $ZIP_PATH | cut -f1))"
