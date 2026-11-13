"""Read-only verification of the closed phase; never regenerates an artifact."""

import hashlib
import json
from pathlib import Path
import sys


def main():
    root = Path(__file__).resolve().parents[1]
    inventory = root/"docs/archive/particle-phase-freeze-v1.json"
    data = json.loads(inventory.read_text())
    failures = []
    for group in ("files", "legacy_implementation_files"):
        for name, expected in data[group].items():
            path = root/name
            if not path.is_file():
                failures.append(f"MISSING {name}")
                continue
            with path.open("rb") as file:
                actual = hashlib.file_digest(file, "sha256").hexdigest()
            if actual != expected:
                failures.append(f"CHANGED {name}")
    if failures:
        print("\n".join(failures), file=sys.stderr)
        return 1
    print(f"Freeze verified: {len(data['files'])} pre-existing outputs and "
          f"{len(data['legacy_implementation_files'])} legacy implementation/configuration files unchanged.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
