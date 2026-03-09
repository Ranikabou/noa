#!/usr/bin/env python3
"""Smoke test: health and project create. Requires API running (e.g. uvicorn noa_api.main:app)."""
import os
import sys
import urllib.request
import json

def main():
    base = os.environ.get("NOA_API_URL", "http://localhost:8000")
    try:
        with urllib.request.urlopen(f"{base}/v1/health", timeout=5) as r:
            data = json.loads(r.read().decode())
            assert data.get("status") == "ok", data
        print("Health OK")
        req = urllib.request.Request(
            f"{base}/v1/projects?name=Smoke&owner_id=00000000-0000-0000-0000-000000000001",
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=5) as r:
            data = json.loads(r.read().decode())
            assert data.get("schema_version") == "1.0" and data.get("id"), data
        print("Project create OK")
        return 0
    except Exception as e:
        print("Smoke test failed:", e, file=sys.stderr)
        return 1

if __name__ == "__main__":
    sys.exit(main())
