# INF2005 ACW1 – Image & Audio Steganography with Digital Signatures

GUI tool that hides a signed verification payload inside a PNG image or WAV audio file using
LSB replacement, then extracts it and verifies it (Ed25519 signature + SHA-256 media hash).

## Setup

Requires Python 3.12 (3.11+ should work).

```
py -3.12 -m venv .venv
.venv\Scripts\activate          # Windows  (macOS/Linux: source .venv/bin/activate)
pip install -r requirements.txt
```

## Running

```
python -m stego.gui             # GUI: Sender, Receiver and Keys tabs
python -m stego.cli --help      # command line version of the same thing
python -m stego.cli capacity cover.png -k 1 --msg-file long.txt   # exact size check, no embedding
python -m pytest                # tests
```

First time: open the **Keys** tab (or run `python -m stego.cli keygen`) to create
`keys/private_key.pem` and `keys/public_key.pem`. The private key is gitignored and only the public
key is submitted. The key pair is generated just for this assignment demo.

## Workflow

1. **Sender (A):** choose a cover (PNG/BMP/WAV), type or pick a message, choose 1–8 LSBs, enter a
   stego key (shared secret), optionally tick *Encrypt*, then *Protect & save*. Before/after
   previews let you view both images or play both audio files.
2. Send the stego file to B by any channel, e.g. as an email attachment (done by hand, not by this tool).
3. **Receiver (B):** load the stego file, enter the same stego key and the sender's public key, then
   *Extract & verify*.

Verdicts: **Authentic**, **Tampered**, **Signature Invalid**, **Payload Missing**,
**Wrong Start Location**, **Cannot Verify**.

## Design summary

| Part | How |
|---|---|
| Carrier | Image: every RGB byte. Audio: the low byte of each PCM sample only |
| Start location | scrypt(stego key) → HKDF → offset mod carrier length. Not fixed, differs per file |
| Header | 8 bytes (magic, version, k, length), 1 LSB, XOR-masked with a key-derived mask so it can't be found by scanning |
| Payload | JSON: media ID, timestamp, media hash, nonce, LSB count, signer fingerprint, team metadata, message |
| Signature | Ed25519 over the exact payload bytes, 64-byte signature appended |
| Media hash | SHA-256 of the file with only the embedding bits cleared, so any other change is caught |
| Confidentiality | Optional AES-GCM encryption of the message, key derived from the stego key |

## Limitations

- Lossless formats only. JPEG/MP3 re-encoding destroys LSBs, and the tool refuses to save stego files as JPEG.
- Anyone without the stego key can still destroy the payload by overwriting LSBs, but can't read or
  forge it. Higher LSB counts are easier to detect by steganalysis and more visible or audible.
- A wrong stego key and a file with no payload both show *Wrong Start Location*, because without the key
  the two cases look the same.

## Folder structure

```
stego/core/   media, LSB, crypto, payload, protect/verify (no GUI code)
stego/gui/    PySide6 app
stego/cli.py  command line
tests/        pytest suite
keys/         key pair (public key only is committed)
samples/      demo cover/stego/tampered files
```
