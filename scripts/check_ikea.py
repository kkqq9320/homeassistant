"""공식 HA 이미지에서 저장소의 unittest를 실행한다."""

import argparse
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
MATRIX = json.loads((ROOT / "tests/ikea_runtime_matrix.json").read_text(encoding="utf-8"))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    versions = parser.add_mutually_exclusive_group(required=True)
    versions.add_argument("--ha-version", choices=list(MATRIX.values()))
    versions.add_argument("--all", action="store_true")
    parser.add_argument("tests", nargs="*")
    args = parser.parse_args()
    selected = list(MATRIX.values()) if args.all else [args.ha_version]
    for version in selected:
        image = f"ghcr.io/home-assistant/home-assistant:{version}"
        available = subprocess.run(["docker", "image", "inspect", image], capture_output=True)
        if available.returncode:
            subprocess.run(["docker", "pull", image], check=True)
        print(f"\nHA {version}", flush=True)
        subprocess.run(["docker", "image", "inspect", image, "--format",
                        "{{.Id}} {{json .RepoDigests}}"], check=True)
        command = ["docker", "run", "--rm", "--network", "none", "--entrypoint", "python",
                   "--mount", f"type=bind,source={ROOT},target=/workspace,readonly",
                   "--workdir", "/workspace", image, "-B", "-m", "unittest"]
        command += [*args.tests, "-v"] if args.tests else ["discover", "-s", "tests", "-p", "test_*.py", "-v"]
        result = subprocess.run(command)
        if result.returncode:
            return result.returncode
    return 0


if __name__ == "__main__":
    sys.exit(main())
