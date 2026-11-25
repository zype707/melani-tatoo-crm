#!/usr/bin/env bash
# Build de Render: instala dependencias y recopila estáticos (WhiteNoise los sirve).
set -o errexit
pip install --upgrade pip
pip install -r requirements.txt
python manage.py collectstatic --noinput
