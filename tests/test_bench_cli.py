import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parents[1]


def test_bench_cli_status_json() -> None:
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "bench_cli.py"),
         "--scenario", "status", "--repeat", "1", "--warmup", "0", "--json"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["benchmark"] == "pd-cli"
    assert payload["results"][0]["scenario"] == "status"
    assert payload["results"][0]["runs"] == 1
    assert payload["results"][0]["median_ms"] > 0
