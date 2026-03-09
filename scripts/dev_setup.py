#!/usr/bin/env python3
"""Dev setup: create .env.example, check Docker, optionally run migrations."""
import os
import subprocess
import sys

def main():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    env_example = os.path.join(root, ".env.example")
    if not os.path.exists(env_example):
        with open(env_example, "w") as f:
            f.write("""# NOA local dev. Copy to .env and adjust.
DATABASE_URL=postgresql://noa:noa@localhost:5433/noa
REDIS_URL=redis://localhost:6379
QDRANT_URL=http://localhost:6333
S3_ENDPOINT_URL=http://localhost:4566
AWS_REGION=us-east-1
S3_BUCKET_ASSETS=noa-assets
JWT_SECRET=dev-secret-change-in-production
""")
        print("Created .env.example")
    print("Start stack: docker compose up -d")
    print("Migrations: DATABASE_URL=... alembic -c db/alembic.ini upgrade head")
    return 0

if __name__ == "__main__":
    sys.exit(main())
