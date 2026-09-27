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
python -m stego.gui             # GUI: Sender, Receiver, Attack Lab and Keys tabs
python -m stego.cli --help      # command line version of the same thing
python -m stego.cli capacity cover.png -k 1 --msg-file long.txt   # exact size check, no embedding
python -m pytest                # tests
python tools/generate_evidence.py   # rebuild tests/evidence/ (logs, screenshots, results.json)
```

The test evidence (every demo case, the Attack Lab runs and the LSB 1-8 table) is summarised in
`tests/evidence/INF2005_ACW1_P6-4_Test_Evidence.docx`.

## Keys

Two different secrets are used here, and they are not the same thing:

- **Signing key pair (Ed25519):** one private key, one public key. The sender signs the payload with
  the private key; the receiver checks the signature with the public key. The team's demo pair is
  already in `keys/`. **Don't regenerate it** (Keys tab or `stego.cli keygen`): a new pair won't
  verify files signed with the team key.
- **Stego key:** a shared passphrase typed into both the Sender and Receiver tabs. It is not a file
  and not the same as the signing key pair above. It derives the payload's start location and the
  optional AES-GCM encryption key.

What to share with the receiver: your **public key** (`public_key.pem`) and the **stego key**
(passphrase), agreed on separately from the stego file itself, e.g. in person or over a different
channel.

In a real deployment the **private key** (`private_key.pem`) would never leave the signer's machine:
anyone holding it can sign payloads that falsely appear to come from you. Here it is committed on
purpose, because the key pair was generated solely for this assignment demo (the spec allows
submitting demo-only keys) and every team member needs the same key to sign and verify. Treat it as
public and never reuse it for anything real.

## Workflow

1. **Sender (A):** choose a cover (PNG/BMP/WAV), type or pick a message, choose 1–8 LSBs, enter a
   stego key (shared secret), optionally tick *Encrypt*, then *Protect & save*. Before/after
   previews let you view both images or play both audio files.
2. Send the stego file to B by any channel, e.g. as an email attachment (done by hand, not by this tool).
3. **Receiver (B):** load the stego file, enter the same stego key and the sender's public key, then
   *Extract & verify*.
4. **Attack Lab:** load a genuine stego file with its stego key and public key, then *Run all
   attacks*. Nine attacks (editing the media, flipping a payload bit, wrong key, cropping, pasting the
   payload into another file, JPEG, replay…) each run on a copy, and the table shows whether
   `verify()` caught each one with the expected verdict.

Verdicts: **Authentic**, **Tampered**, **Signature Invalid**, **Payload Missing**,
**Wrong Start Location**, **Cannot Verify**, and our own **Replay Detected**.

Replay detection remembers every accepted payload (`keys/seen_nonces.json`, not committed), so
verifying the same file a second time on the same computer says **Replay Detected**. Before a demo,
press **Clear replay history** in the Receiver tab (or run `python -m stego.cli clear-replay`) so
files verified during rehearsal start fresh.

## M2 audio demo assets

Generate the reproducible M2 WAV cover, long-message stego file and amplified
tamper case with:

```
.venv\Scripts\python tools\generate_audio_samples.py
```

The files are written to `samples/audio/`. Use its `README.md` for the demo
stego key, public key, verification commands and the precise Audacity workflow.
The GUI WAV previews include a waveform, allowing a before/after comparison.

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
