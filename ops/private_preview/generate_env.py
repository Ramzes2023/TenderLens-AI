"""Wrapper runs on remote preview host; writes NEW preview-only env, prints no secrets."""
import argparse
import os
from pathlib import Path
import secrets


def generate(path):
    path = Path(path)
    # Exclusive create: never overwrite an existing configuration or rotate its DB password.
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as output:
        output.write("PREVIEW_DB_PASSWORD=" + secrets.token_hex(32) + "\n")
        output.write("PREVIEW_APP_SECRET=" + secrets.token_hex(32) + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("path", help="New env path inside the isolated preview directory")
    arguments = parser.parse_args()
    generate(arguments.path)
    print("Created preview-only environment; values withheld.")
