#!/usr/bin/env python3
"""Wait for Postgres to accept connections. Retries for up to 60 seconds."""
import os
import sys
import time

import psycopg2
from psycopg2 import OperationalError

DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql://noa:noa@localhost:5433/noa",
)
MAX_ATTEMPTS = 30
SLEEP_SEC = 2


def main():
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            conn = psycopg2.connect(DATABASE_URL)
            conn.close()
            print("Postgres is ready.", file=sys.stderr)
            return 0
        except OperationalError as e:
            if attempt < MAX_ATTEMPTS:
                print(f"Waiting for Postgres (attempt {attempt}/{MAX_ATTEMPTS})...", file=sys.stderr)
                time.sleep(SLEEP_SEC)
            else:
                print(f"Postgres not ready after {MAX_ATTEMPTS} attempts: {e}", file=sys.stderr)
                return 1
    return 1


if __name__ == "__main__":
    sys.exit(main())
