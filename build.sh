#!/usr/bin/env bash
# Render build script. Runs on every deploy before the web service starts.
# Exit on first error so a failure stops the deploy cleanly.
set -o errexit

echo "==> Installing Python dependencies"
pip install --upgrade pip
pip install -r requirements.txt

echo "==> Collecting static files (Django)"
cd app/ui
python manage.py collectstatic --no-input

echo "==> Applying database migrations"
python manage.py migrate --no-input

echo "==> Build complete"
