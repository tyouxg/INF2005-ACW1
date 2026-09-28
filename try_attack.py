"""Run the Attack Lab from the command line and narrate each attack.

    python try_attack.py                                   # the P1 evidence image
    python try_attack.py <stego file> <stego key> <public key .pem>

Same thing the Attack Lab tab does (stego/core/attacks.py), printed as a story:
for each attack, what the attacker has and does, which of verify()'s checks it
goes after, and what verify() said back. Handy for rehearsing the demo.
"""

import sys

from stego.core import attacks, crypto, media, protect

path = sys.argv[1] if len(sys.argv) > 1 else "tests/evidence/files/p1_image_stego.png"
key = sys.argv[2] if len(sys.argv) > 2 else "p6-4-demo-key"
pub = crypto.load_public_key(sys.argv[3] if len(sys.argv) > 3 else "keys/public_key.pem")
stego = media.load_cover(path)

# Defender side first: the file has to be genuine, and verifying it tells us
# where the payload is (only because we hold the stego key)
with attacks.scratch_replay_store():
    base = protect.verify(stego, key, pub)
d = base.details
print(f"File: {path} ({stego.describe()})")
print(f"Genuine file verifies as: {base.verdict}")
if base.verdict != protect.AUTHENTIC:
    sys.exit("The attacks need a genuine stego file to start from.")
region = attacks.payload_region(d)
print(f"Payload: starts at carrier byte {d['start']:,}, uses {len(region):,} of "
      f"{d['carrier_units']:,} carrier bytes, k={d['k']}, repetition x{d.get('reps', 1)}, "
      f"format v{d.get('version', 1)}")
print("Every attack below runs on its own fresh copy of this file.\n")

results = attacks.run_all(stego, key, pub)
for r in results:
    if r.number in (1, 9):
        part = ("PART 1: attacks on verify()'s checks, in the order it runs them" if r.number == 1
                else "PART 2: damage in transit (robustness and our limitation)")
        print("=" * 78 + f"\n{part}\n" + "=" * 78)
    print(f"Attack {r.number}: {r.name}   [targets check {r.check}]")
    print(f"  Attacker has : {r.attacker_has}")
    print(f"  Attacker does: {r.what}")
    print(f"  Defender says: {r.got}  ({r.reason})")
    print(f"  Expected     : {' / '.join(r.expected)}  -> {'CAUGHT as expected' if r.passed else 'NOT AS EXPECTED'}"
          f"   | signed payload recovered: {'yes' if r.recovered else 'no'}\n")

caught = sum(r.passed for r in results)
print(f"{caught} of {len(results)} attacks gave the expected verdict; "
      f"the signed payload survived {sum(r.recovered for r in results)} of them.")
