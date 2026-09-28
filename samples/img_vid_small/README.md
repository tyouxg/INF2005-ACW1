# Small files for the capacity check (Raffael)

In the Sender tab pick `tiny_24x24.png` (or the 4-frame `tiny_24x24.mkv`) as the cover and *Load .txt* `project_overview.txt`: the capacity line turns red (DOES NOT FIT) at 1 LSB, and pressing Protect shows the capacity-check error. Raise the LSBs to see where it starts to fit.

Stego key: `p6-4-demo-key` · Public key: `keys/public_key.pem` · Made by `tools/make_demo_samples.py` (every row below was checked when it ran).

| File | Verify gives | Notes |
|---|---|---|
| `tiny_24x24.png + project_overview.txt` | needs 1,092 bytes; DOES NOT FIT at 1 LSB (208 bytes), first fits at 6 LSBs | capacity check |
| `tiny_24x24.png + learning_outcome.txt` | needs 525 bytes; DOES NOT FIT at 1 LSB (208 bytes), first fits at 3 LSBs | capacity check |
| `tiny_24x24.mkv + project_overview.txt` | needs 1,092 bytes; DOES NOT FIT at 1 LSB (856 bytes), first fits at 2 LSBs | capacity check |
| `tiny_24x24.mkv + learning_outcome.txt` | needs 525 bytes; fits at 1 LSB (856 bytes) | capacity check |

Before a demo, press **Clear replay history** in the Receiver tab (or run `python -m stego.cli clear-replay`), or a file you already verified will say Replay Detected.
