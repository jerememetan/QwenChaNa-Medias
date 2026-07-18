"""
Quick helper to POST to /generate using the FastAPI TestClient.
Run with your virtualenv Python (this repo uses `.venv`):

PowerShell (no activation):
    .\.venv\Scripts\python.exe run_test.py

Git Bash / WSL:
    ./.venv/Scripts/python.exe run_test.py

If dependencies are missing, run:
    .\.venv\Scripts\python.exe -m pip install -r requirements.txt
"""

from backend.main import create_production_app
from fastapi.testclient import TestClient
import json
import sys


def main():
    app = create_production_app()
    client = TestClient(app)
    resp = client.post('/generate', json={'prompt': 'A 30 second explainer about space'})
    print('Status:', resp.status_code)
    try:
        print('Response:', json.dumps(resp.json(), indent=2))
    except Exception:
        print('Response (raw):', resp.text)
    return 0


if __name__ == '__main__':
    sys.exit(main())
