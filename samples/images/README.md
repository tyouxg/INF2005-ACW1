# M1 image demo files

Stego key: `p6-4-demo-key`. Public key: `keys/public_key.pem`.

The stego, tampered and re-saved files are made by `tools/generate_image_samples.py`, which also
checks every file gives the verdict below before it finishes:

```
.venv\Scripts\python tools\generate_image_samples.py
```

| File | What it is | Expected verdict |
|---|---|---|
| `demo1.png` | Cover, 666x300 PNG (palette PNG, loaded as RGB) | — |
| `demo3.jpg` | Cover, 600x360 **JPEG** (JPEG is accepted as a cover, never as output) | — |
| `demo2.txt` | Message file for *Load .txt* in the Sender tab | — |
| `demo567.png` | M3's cover for the custom encrypted payload demo | — |
| `demo1_stego_k2.png` | `demo1.png` + short message (learning outcome), 2 LSBs | **Authentic** |
| `demo1_long_k1.png` | `demo1.png` + long message (project overview), 1 LSB. PSNR 69.6 dB | **Authentic** |
| `demo1_long_k8.png` | Same message at 8 LSBs. PSNR 32.1 dB, payload rows visibly noisy | **Authentic** |
| `demo3_jpeg_cover_stego.png` | `demo3.jpg` cover, short message, 2 LSBs, saved as PNG | **Authentic** |
| `demo1_tampered.png` | `demo1_stego_k2.png` with a black bar painted away from the payload | **Tampered** |
| `demo1_stego_resaved.jpg` | `demo1_stego_k2.png` re-saved as JPEG (quality 95) | **Wrong Start Location** |

Why the last two differ: the black bar misses the payload, so the signature is still valid and only
the media hash catches the change (**Tampered**). JPEG re-encoding changes the low bits everywhere,
including the hidden header, so the payload can't even be found (**Wrong Start Location**).

Quick checks:

```
python -m stego.cli verify samples/images/demo1_stego_k2.png --key p6-4-demo-key --pub keys/public_key.pem
python -m stego.cli verify samples/images/demo1_tampered.png --key p6-4-demo-key --pub keys/public_key.pem
python -m stego.cli verify samples/images/demo1_stego_resaved.jpg --key p6-4-demo-key --pub keys/public_key.pem
```

Clear the replay history first (`python -m stego.cli clear-replay`), otherwise a file you've already
verified says **Replay Detected**.

Screenshots and the CLI log for these are in `tests/evidence/` (`screenshots/P5_*.png`, `P6_*.png`, `psnr_k1.png`,
`psnr_k8.png` and `logs/P6.txt`).

To tamper by hand for the demo: protect `demo1.png` in the Sender tab, note the payload rows in the
Sender log ("Payload sits in image rows …"), then open the stego file in Paint, draw a mark on other
rows, save as PNG and verify: **Tampered**. A mark over the payload rows breaks the payload itself,
so it fails earlier (usually **Signature Invalid**, or **Wrong Start Location** if it hits the header).
