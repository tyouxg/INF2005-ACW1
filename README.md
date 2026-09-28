# INF2005 ACW1 – Image & Audio Steganography with Digital Signatures (Team P6-4)

GUI tool that hides a signed verification payload inside an image (PNG/BMP, JPG covers), WAV audio
or lossless video using LSB replacement, then extracts it and verifies it (Ed25519 signature +
SHA-256 media hash), with an Attack Lab and a Steganalysis tab for the optional challenges.

## Setup

Requires Python 3.12 (tested on 3.12 and 3.14; `requirements.txt` pins exact versions for both).

```
py -3.12 -m venv .venv
.venv\Scripts\activate          # Windows  (macOS/Linux: source .venv/bin/activate)
pip install -r requirements.txt
```

## Running

```
python -m stego.gui             # GUI: Sender, Receiver, Attack Lab, Steganalysis and Keys tabs
python -m stego.cli --help      # command line version of the same thing
python -m stego.cli capacity cover.png -k 1 --msg-file long.txt   # exact size check, no embedding
python -m stego.cli scan file.png   # steganalysis, no key needed
python -m stego.cli clear-replay    # forget accepted payloads (do this before a demo)
python -m pytest                # tests
python try_attack.py            # narrated Attack Lab run on the P1 evidence image
python tools/generate_evidence.py   # rebuild tests/evidence/ (logs, screenshots, results.json)
```

Always run from the project root as modules (`python -m stego.gui`), not `python app.py`.

The test evidence (every demo case, the Attack Lab runs and the LSB 1-8 table) is summarised in
`tests/evidence/INF2005_ACW1_P6-4_Test_Evidence.docx`.

## Expected outputs

| Command | You should see |
|---|---|
| `python -m pytest` | `89 passed` |
| `python -m stego.cli verify tests/evidence/files/p1_image_stego.png --key p6-4-demo-key` | `Verdict: Authentic` and the hidden message |
| same, with `n2_image_tampered.png` | `Verdict: Tampered` |
| same, with `n4_image_forged.png` | `Verdict: Signature Invalid` |
| same, with `--key wrong` | `Verdict: Wrong Start Location` |
| same file verified twice | second time: `Verdict: Replay Detected` (clear with `clear-replay`) |
| `python try_attack.py` | 11 of 11 attacks give the expected verdict |
| `python -m stego.cli scan tests/evidence/files/s1_legacy_v1_stego.png` | readable JSON found at k=2 (a version 1 file) |
| `python -m stego.cli scan tests/evidence/files/p1_image_stego.png` | nothing readable (version 2 masks the body) |

## Sample files

All stego files below verify with `keys/public_key.pem` unless noted. Stego key for our evidence
files: `p6-4-demo-key`.

| Type | Original (cover) | Protected (stego) → Authentic | Tampered / negative |
|---|---|---|---|
| Image | `tests/evidence/files/image_cover.png`, `samples/images/demo1.png`, `samples/images/demo3.jpg` (JPEG cover) | `tests/evidence/files/p1_image_stego.png` (k=2), `p3_image_custom_encrypted.png` (AES-GCM), `r1_image_robust_x5.png` (robust) | `n2_image_tampered.png` → Tampered, `n4_image_forged.png` → Signature Invalid, `image_tiny.png` → capacity check fails |
| Audio | `tests/evidence/files/audio_cover.wav`, `samples/audio/cover_stereo_music.wav` | `tests/evidence/files/p2_audio_stego.wav`, `p4_audio_custom_k8.wav`; `samples/audio/stego_long_message.wav` (key `m2-audio-demo-key`, public key `samples/audio/demo_public_key.pem`) | `n3_audio_tampered.wav` → Tampered; `samples/audio/tampered_amplified_section.wav` → Tampered |
| Video | `tests/evidence/files/video_cover.mkv` | `v1_video_stego.mkv` | `v2_video_tampered.mkv` → Tampered |

`samples/images/demo2.txt` is a message file for *Load .txt*. The `samples/audio/*_k1/_k4/_k8`
files are M2's listening-test files (see `tests/evidence/audio-audibility.md`).

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

1. **Sender (A):** choose a cover (PNG/BMP/JPG, WAV, or MKV/AVI/MP4 video), type or pick a message,
   choose 1–8 LSBs, enter a stego key (shared secret), optionally tick *Encrypt* and pick a
   *Robustness* level, then *Protect & save*. Before/after previews let you view both images, play
   both audio files or step through video frames; the difference view shows where the payload went.
2. Send the stego file to B by any channel, e.g. as an email attachment (done by hand, not by this tool).
3. **Receiver (B):** load the stego file, enter the same stego key and the sender's public key, then
   *Extract & verify*.
4. **Attack Lab:** load a genuine stego file with its stego key and public key, then *Run all
   attacks*. 11 attacks, numbered in the order `verify()` runs its checks (1–3 find the header,
   4 length, 5 signature, 6–7 media hash, 8 replay; 9–11 are damage in transit), each run on a fresh
   copy. The table shows the check each one targets, the verdict and whether the payload survived.
5. **Steganalysis:** load any file and scan it without a key.

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
| Carrier | Image: every RGB byte. Audio: the low byte of each PCM sample only. Video: every RGB byte of every frame |
| Start location | scrypt(stego key) → HKDF → offset mod carrier length. Not fixed, differs per file (for video it picks the frame) |
| Header | 8 bytes (magic, version, k, length), 1 LSB, XOR-masked with a key-derived mask so it can't be found by scanning |
| Payload | JSON: media ID, timestamp, media hash, nonce, LSB count, signer fingerprint, team metadata, message |
| Signature | Ed25519 over the exact payload bytes, 64-byte signature appended |
| Body mask (format v2) | Payload + signature XOR-masked with a key-derived SHAKE-256 stream, so the LSBs look like noise |
| Media hash | SHA-256 of the file with only the embedding bits cleared, so any other change is caught |
| Confidentiality | Optional AES-GCM encryption of the message, key derived from the stego key |
| Robust mode | Optional: every bit stored x3/x5/x7 times, read back by majority vote |

## Optional challenges

- **Video covers.** MKV/AVI saved as FFV1 (lossless, via the ffmpeg that `imageio-ffmpeg` ships).
  MP4/MOV are accepted as covers but never written, because H.264 is lossy. The GUI shows frames
  with a slider, and the difference view jumps to the frame the key picked. Every frame is held in
  memory as raw pixels (1080p is ~187 MB per second), so the limit is 400 MB: for a phone video the
  Sender offers to make a 5 s, 640 px wide lossless copy (`python -m stego.cli shrink-video in.mp4 out.mkv`).
- **Robust embedding.** *Robustness* in the Sender tab (`--robust 5` on the CLI). The payload survives
  a flipped bit, 1% LSB noise or a scratch over it, and the verdict still reports the change as
  Tampered. The Attack Lab's *Payload recovered* column shows the difference.
- **Steganalysis.** The *Steganalysis* tab (`python -m stego.cli scan <file>`) looks for hidden data
  with no key at all: the textbook chi-square attack, and a structure scan that found and read our
  own version 1 payloads. That's why format version 2 masks the whole body. Version 1 files still
  verify.
- **Attack simulation.** The *Attack Lab* tab runs 11 attacks on a genuine file.

## Limitations

- Lossless formats only. JPEG/MP3/H.264 re-encoding destroys LSBs, even in robust mode, and the tool
  refuses to save stego files in lossy formats.
- Anyone without the stego key can still destroy the payload by overwriting LSBs, but can't read or
  forge it. Higher LSB counts are easier to detect and more visible or audible.
- Files made with format version 1 (before the body mask) can be found and read by the structure scan.
- The chi-square attack can't tell our covers from stego files, since real photos and audio already
  have noisy low bits. A stronger statistical test might still flag big payloads.
- Robust mode divides capacity by the repetition factor. Video keeps no audio track and every frame is
  held in memory.
- Transparent PNGs lose their transparency: the alpha channel is dropped, so transparent areas turn
  black in the stego image.
- The replay log is per computer and nothing checks how old the timestamp is.
- A wrong stego key and a file with no payload both show *Wrong Start Location*, because without the key
  the two cases look the same.

## Folder structure

```
stego/core/      media, LSB, crypto, payload, protect/verify, robust, attacks, steganalysis (no GUI code)
stego/gui/       PySide6 app (Sender, Receiver, Attack Lab, Steganalysis, Keys)
stego/cli.py     command line
tests/           pytest suite
tests/evidence/  test evidence: logs, screenshots, files used, results.json and the Word write-up
tools/           evidence generator, audio sample generator
try_attack.py    narrated Attack Lab run
keys/            the team's demo key pair (both keys committed on purpose, see Keys)
samples/         demo covers, stego and tampered files (images, audio)
```

## Acknowledgements and AI use

- **Libraries:** PySide6 (Qt), NumPy, Pillow, cryptography, matplotlib, imageio-ffmpeg (bundles
  FFmpeg), pytest.
- **Media:** the evidence photo is Grace Hopper's portrait (U.S. Navy, public domain), shipped with
  matplotlib's sample data. The evidence audio and `samples/audio` covers are synthetic tones generated
  by `tools/generate_audio_samples.py`. The `samples/images` files were supplied by M1.
- **Algorithms:** Ed25519 (RFC 8032), HKDF (RFC 5869), scrypt (RFC 7914), AES-GCM, SHA-256, SHAKE-256;
  the chi-square attack from Westfeld & Pfitzmann, "Attacks on Steganographic Systems" (2000).
- **AI assistance:** parts of the code, tests and documentation were written with an AI coding
  assistant (Claude Code, by Anthropic). This includes the initial project scaffold and, for M6, the
  Attack Lab, robust mode, video support, the steganalysis structure scan, the evidence generator and
  explanatory notes. Every AI-assisted part was reviewed by the team, run on real files and checked by
  the automated tests (89 passing), and each member can explain their own part.
