"""Claude-Desktop-Konfiguration mit absoluten Pfaden erzeugen, ohne Geheimnisse."""
import json
from pathlib import Path
import sys


def config() -> dict:
    return {"mcpServers": {"log-observatory": {
        "command": str(Path(sys.executable).resolve()),
        "args": [str(Path(__file__).resolve().parent / "run.py")],
    }}}


if __name__ == "__main__":
    print(json.dumps(config(), indent=2))
