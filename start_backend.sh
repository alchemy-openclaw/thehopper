#!/bin/bash
set -e
cd /home/openclaw/projects/thehopper/backend
source venv/bin/activate

# Load backend .env
set -a
. ./.env
set +a

# Load Twilio from Hermes .env
TWILIO_ACCOUNT_SID=$(grep TWILIO_ACCOUNT_SID ~/.hermes/.env | cut -d= -f2)
TWILIO_AUTH_TOKEN=$(grep TWILIO_AUTH_TOKEN ~/.hermes/.env | cut -d= -f2)
TWILIO_FROM_NUMBER=$(grep TWILIO_PHONE_NUMBER ~/.hermes/.env | cut -d= -f2)
export TWILIO_ACCOUNT_SID TWILIO_AUTH_TOKEN TWILIO_FROM_NUMBER

echo "Starting thehopper backend on port 8001"
exec python -m uvicorn main:app --host 0.0.0.0 --port 8001
