#!/usr/bin/env python3
"""Start the thehopper backend with all env vars loaded."""
import os
import subprocess
import sys

# Load backend .env
backend_dir = os.path.dirname(os.path.abspath(__file__))
env_path = os.path.join(backend_dir, "backend", ".env")
hermes_env = os.path.expanduser("~/.hermes/.env")

env = os.environ.copy()

# Load backend .env
with open(env_path) as f:
    for line in f:
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            env[k] = v

# Load Twilio from Hermes .env
with open(hermes_env) as f:
    for line in f:
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            if k == "TWILIO_PHONE_NUMBER":
                env["TWILIO_FROM_NUMBER"] = v
            elif k.startswith("TWILIO"):
                env[k] = v

# Start uvicorn
cmd = [sys.executable, "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8001"]
os.chdir(os.path.join(backend_dir, "backend"))
os.execvpe(cmd[0], cmd, env)
