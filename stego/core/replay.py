"""Local record of which payload nonces have already been verified.

Used to detect replay: the exact same signed payload being presented again as
if it were new. This is not part of the spec's suggested verdicts, it's a
team addition for a stronger integrity story.
"""

import json
from pathlib import Path

DEFAULT_STORE = Path(__file__).resolve().parents[2] / "keys" / "seen_nonces.json"

# Reads the store file and returns every nonce seen so far as a set.
# Returns an empty set if the file doesnt exist yet (first run).
def _load(path: Path) -> set[str]:
    if not path.exists():
        return set()
    return set(json.loads(path.read_text(encoding="utf-8")))

# Checks whether this nonce has alr been recorded, meaning this exact
# payload has been verified before and this file may be a replay.
def seen_before(nonce: str, path: Path = DEFAULT_STORE) -> bool:
    return nonce in _load(path)

# Add this nonce to the store so future checks will catch it if reused.
# Called only after a payload passes every other check (signature, hash).
def record(nonce: str, path: Path = DEFAULT_STORE) -> None:
    seen = _load(path)
    seen.add(nonce)
    # Makes sure the keys/ folder exists first, incase it is a fresh checkout
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(sorted(seen)), encoding="utf-8")