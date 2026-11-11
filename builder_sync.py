"""
Keep the Zigbert builder's adverts database in step with the portal.

Called at the end of add_modelled.py and build_scraped4.py: after the portal's
files change, the same dataset is replaced in the builder's Supabase table by
zigbert-platform/engine/load_adverts.py --only <name> (one transaction, minutes).
Skip with --no-builder. Needs zigbert-platform cloned next to this repo (or
ZIGBERT_PLATFORM set) with SUPABASE_DB_PASSWORD in its .env.local.
"""
import os
import subprocess
import sys
from pathlib import Path

PLATFORM = Path(os.environ.get("ZIGBERT_PLATFORM") or Path(__file__).resolve().parent.parent / "zigbert-platform")


def sync(name):
    loader = PLATFORM / "engine" / "load_adverts.py"
    if not loader.exists():
        print(f"\nBuilder NOT updated: {loader} not found. Run it there with --only {name}.")
        return 1
    print(f"\nUpdating the builder's adverts database ({name})…", flush=True)
    r = subprocess.run([sys.executable, str(loader), "--only", name], cwd=PLATFORM,
                       env=dict(os.environ, ZIGBERT_QUARTERS=str(Path(__file__).resolve().parent / "quarters")))
    if r.returncode:
        print(f"Builder NOT updated (exit {r.returncode}). The portal files are fine; rerun:\n"
              f"  cd {PLATFORM} && python3 engine/load_adverts.py --only {name}")
    return r.returncode
