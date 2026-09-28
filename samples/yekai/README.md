# M6 demo files (Ye Kai)

Attack Lab: load `stego_normal.png`, then `stego_robust_x5.png`, and compare rows 5, 9 and 10. Robust demo: verify each `*_scratched.png` / `*_noise.png` pair in the Receiver tab. The normal file loses its payload, the robust one keeps it. Video: verify `video_stego.mkv` then `video_tampered.mkv`.

Stego key: `p6-4-demo-key` · Public key: `keys/public_key.pem` · Made by `tools/make_demo_samples.py` (every row below was checked when it ran).

| File | Verify gives | Notes |
|---|---|---|
| `cover.png` | no payload (the original) | Grace Hopper portrait, 400x469, public domain |
| `stego_normal.png` | Authentic | k=2, payload in image rows 411-412 (y coordinates) |
| `stego_robust_x5.png` | Authentic | k=2, x5 repetition, payload in image rows 411-420 (y coordinates) |
| `normal_scratched.png` | Signature Invalid | black 60x4 box at x=100, y=412, over the payload rows |
| `robust_x5_scratched.png` | Tampered, message still readable | black 60x4 box at x=100, y=412, over the payload rows (same box) |
| `normal_noise.png` | Payload Missing | lowest bit of 1% of all carrier bytes flipped |
| `robust_x5_noise.png` | Tampered, message still readable | same 1% noise |
| `video_cover.mkv` | no payload (the original) | 24 frames, 320x240, 12 fps |
| `video_stego.mkv` | Authentic | k=2, payload in frame 24, rows 8-10 |
| `video_tampered.mkv` | Tampered, message still readable | black box in frame 1 (the payload is in frame 24) |

Before a demo, press **Clear replay history** in the Receiver tab (or run `python -m stego.cli clear-replay`), or a file you already verified will say Replay Detected.
