"""Configure the DagsHub DVC remote from .env and check storage access. Run once per member.

    python scripts/configure_dvc_remote.py

Reads DAGSHUB_REPO_OWNER, DAGSHUB_REPO, DAGSHUB_USER and DAGSHUB_TOKEN from .env.
The token goes only into .dvc/config.local (git-ignored) and is never printed.
Teammates keep the shared owner/repo and put their OWN user + token in .env; the repo owner must
add them as collaborators on DagsHub (repo -> Settings -> Collaborators) so they can push.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from solarcast.config import env
from solarcast.data import storage

DVC = str(Path(sys.executable).with_name("dvc"))


def dvc(*args: str, secret: bool = False) -> None:
    shown = " ".join((*args[:-1], "****")) if secret else " ".join(args)
    print(f"  dvc {shown}")
    subprocess.run([DVC, *args], cwd=ROOT, check=True)


def main() -> int:
    owner, repo = env("DAGSHUB_REPO_OWNER") or "", env("DAGSHUB_REPO") or ""
    user, token = env("DAGSHUB_USER") or "", env("DAGSHUB_TOKEN") or ""
    missing = [k for k, v in {"DAGSHUB_REPO_OWNER": owner, "DAGSHUB_REPO": repo,
                              "DAGSHUB_USER": user, "DAGSHUB_TOKEN": token}.items()
               if not v or "<" in v]
    if missing:
        print(f"ERROR: fill in {', '.join(missing)} in .env (copy from .env.example)")
        return 1

    print(f"Configuring DVC remote 'origin' -> DagsHub {owner}/{repo} as {user}")
    dvc("remote", "add", "-d", "-f", "origin", "s3://dvc")
    dvc("remote", "modify", "origin", "endpointurl", f"https://dagshub.com/{owner}/{repo}.s3")
    dvc("remote", "modify", "--local", "origin", "access_key_id", token, secret=True)
    dvc("remote", "modify", "--local", "origin", "secret_access_key", token, secret=True)

    print("Checking DagsHub repo bucket ...")
    keys = storage.list_keys()
    print(f"  OK - bucket '{storage.bucket()}' reachable, {len(keys)} objects")
    print("Done. Next: dvc push   (and commit .dvc/config if it changed)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
