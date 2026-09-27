# M2 — Audio Steganography

## Purpose and ownership

M2 owns the WAV-audio steganography work: loading and saving PCM WAV files,
embedding and extracting the signed payload through audio LSBs, and the GUI
audio preview/playback. The relevant shared files are:

- `stego/core/media.py` — `load_audio`, `save_audio`, WAV metadata and the audio
  carrier definition.
- `stego/core/lsb.py` — shared LSB embedding/extraction logic. Coordinate any
  change here with M1 because image steganography uses the same code.
- `stego/gui/widgets.py` — the `MediaView` WAV play/stop controls. Coordinate
  GUI changes with M5.
- `tests/test_core.py` and `samples/audio/` — M2 audio coverage and demo assets.

Do not rewrite working code simply to make it different. Understand and be able
to explain each change made in the owned/shared files.

## Current implementation: what already works

- Only `.wav` is accepted for audio. `load_audio` rejects compressed WAV data;
  `save_audio` writes WAV only.
- The audio bytes are kept unchanged except for `data[0::sampwidth]`: the first
  byte of each little-endian PCM sample. That is the sample's low byte, so there
  is one carrier byte per sample per channel.
- The shared LSB code accepts `k = 1..8`, wraps at the end of the carrier, and
  writes the payload body after an 8-byte protected header.
- Automated coverage now proves PCM round trips for mono/stereo 8-, 16-, and
  24-bit WAV fixtures, confirms non-carrier bytes are unchanged, and checks
  the stereo 10-second capacity calculation. The original 16-bit test still
  covers `k = 1`, `4`, and `8` and an upper-byte audio edit yielding
  **Tampered**.
- The GUI displays WAV metadata, provides Play/Stop through Qt multimedia, and
  renders a normalised waveform in each WAV preview. The Sender tab therefore
  gives a before/after waveform comparison without adding another dependency.
- `samples/audio/` contains a reproducible generated cover, authentic stego
  WAV, same-length amplified tamper WAV, public verification key, and exact
  generation details. No private key is retained.

Still required before the live demo: test team-recorded/licensed speech and
music files, complete the human listening table, check playback on the demo
laptop, and make the requested manual Audacity tamper export.

## Technical facts to explain in the demo

A **sample** is one amplitude value for one channel at one instant. `sampwidth`
is its storage size in bytes. PCM WAV samples here are little-endian, so the
least significant byte comes first. Modifying that low byte changes the signal
least for 16- and 24-bit audio; the implementation therefore uses only it.

For a WAV with `nframes`, `channels`, and sample width `sampwidth`, the number
of carrier bytes is:

```
carrier bytes = nframes × channels
```

The body capacity reported by `protect.capacity_bytes` reserves 64 carrier
units for the 8-byte header:

```
body capacity bytes = floor((carrier bytes - 64) × k / 8)
```

For 10 seconds of 44.1 kHz stereo audio, this is
`10 × 44,100 × 2 = 882,000` carrier bytes. At `k = 2`, the reported body
capacity is `floor((882,000 - 64) × 2 / 8) = 220,484` bytes (about 215.3 KiB).
The payload JSON and 64-byte signature consume part of that capacity, so it is
not all available for visible message text.

At `k = 8`, all bits in the low byte are replaced. On a 16-bit sample the high
byte remains intact, but this is much more audible/detectable than lower `k`.
On 8-bit PCM, the low byte is the entire sample, so `k = 8` replaces every
sample completely and is expected to cause severe distortion. This is a
limitation to demonstrate, not a reason to claim 8-bit audio is transparent.

## In scope

- Verify and, only where evidence shows a real issue, improve PCM WAV
  load/embed/save behaviour in `stego/core/media.py`.
- Maintain correct low-byte-only carrier selection for mono and stereo 8-,
  16-, and 24-bit PCM WAVs; preserve metadata (channels, sample width, sample
  rate, and frame count) when saving.
- Add focused automated tests for audio round trips and carrier-byte behaviour
  across the above formats. Keep all pre-existing tests passing.
- Test real WAVs representing speech, music, stereo, 24-bit, and 8-bit audio.
  Record format, action, result, and any limitation/error rather than assuming
  every externally produced WAV is compatible.
- Create `samples/audio/` demo assets: a cover WAV, a long-message stego WAV,
  and an Audacity-edited tampered WAV, with a short provenance/readme note if
  required by the team.
- Make and record listening comparisons at `k = 1`, `4`, and `8`; give the
  limitations/evidence owner a concise audibility table.
- Work with M5 on an audio waveform or amplified difference comparison in the
  GUI. M2 supplies the audio interpretation and verifies the result; M5 owns
  integration consistency in shared GUI areas.
- Rehearse M2's audio positive and tampered-audio demo, and explain the audio
  implementation and limitations without relying on notes.

## Out of scope

- Image carrier behaviour, transparent-PNG support, JPEG cover/output work
  (M1), except avoiding regressions in the shared `lsb.py`.
- Payload schema, signing, hashing, encryption, key generation, or replay
  design (M3/M4). M2 uses their existing interfaces and reports defects with
  reproducible evidence.
- Overall Sender/Receiver layout, exact-capacity UX, and general GUI polish
  (M5), other than WAV playback and the jointly planned waveform/difference
  view.
- Attack-simulation module, steganalysis feature, and evidence-folder
  coordination (M6), although M2 contributes the audio test assets/results.
- Lossy/compressed audio formats and formats not implemented by the app:
  MP3/AAC/OGG and compressed WAV. Do not promise LSB survival after transcoding
  or lossy re-encoding.
- Implementing email/SMTP transfer code. Any A-to-B email step is performed
  manually outside this project.

## M2 work checklist

- [x] Run the baseline: create the documented virtual environment, install
  requirements, run `python -m pytest`, and launch `python -m stego.gui`.
- [ ] Read and trace `load_audio`/`save_audio`, `Cover.carrier`, `embed`,
  `extract`, `protect`, and `verify` until each line relevant to audio can be
  explained.
- [ ] Make a format-results table for real speech, music, stereo, 24-bit, and
  8-bit PCM WAVs. Include whether load → protect → save → verify succeeds and
  any playback or compatibility observation.
- [x] Add/revise only justified audio handling and add regression tests for all
  supported sample widths/channel layouts.
- [x] Produce a listening/audibility table for the same cover at `k = 1`, `4`,
  and `8` (e.g. no obvious change / noticeable noise / severe distortion), plus
  the listener and playback conditions.
- [x] Add and verify a before/after waveform comparison for WAVs. M5 should
  confirm it behaves correctly in the integrated GUI build.
  display for WAVs.
- [x] Put named, reproducible M2 demo assets in `samples/audio/` and make sure
  they are small enough for the repository/submission rules.
- [x] Generate a stego WAV containing the required long project-overview
  message; on a clean reload, extract it with the shared stego key and public
  key and capture **Authentic**.
- [ ] In Audacity, amplify a section of that stego WAV and export as PCM WAV;
  reload it and capture **Tampered**. Also explain that trimming changes the
  carrier length, hence the key-derived offset, so it normally produces
  **Wrong Start Location** instead.
- [x] Run the complete test suite before the M2 change is merged and rehearse
  the M2 segment of the timed team demo.

## Acceptance criteria for M2

M2 is complete when all of the following are true:

1. **Positive audio demonstration:** Using a supplied PCM WAV and the long
   project-overview message, the app saves a WAV, can play it, then reloads and
   verifies it as **Authentic** with the correct stego key and public key.
2. **Negative audio demonstration:** An Audacity-amplified section of the
   M2 stego WAV, exported as WAV, verifies as **Tampered**. The presenter can
   distinguish this from a trimmed file producing **Wrong Start Location**
   because the carrier length changes the derived offset.
3. **Format evidence:** There is a documented result for real speech, music,
   stereo, 24-bit, and 8-bit WAV inputs. Supported cases have a reproducible
   round trip; unsupported/compressed cases are rejected or clearly documented
   as limitations.
4. **Audio quality evidence:** A recorded listening comparison exists for
   `k = 1`, `4`, and `8`, and the limitations section states the 8-bit and
   higher-`k` trade-offs accurately.
5. **Visual aid:** The GUI has a working, understandable WAV waveform or
   difference comparison, delivered jointly with M5, or the team has agreed
   and documented an equivalent GUI comparison that demonstrably helps show
   before/after audio changes.
6. **Regression safety:** Automated tests cover audio round trips for the
   supported sample-width/channel cases, confirm only the intended carrier
   bytes change, and `python -m pytest` passes in full.
7. **Demo readiness:** `samples/audio/` contains the positive and tampered
   M2 assets, WAV playback works on the demo laptop, and M2 can clearly explain
   samples, sample width, little-endian order, low-byte selection, capacity,
   and the `k = 8` consequence.

## Evidence to hand to the team

- Format compatibility table and audibility table for the limitations/evidence
  section (M6).
- Screenshots or screen recording of the positive **Authentic** and negative
  **Tampered** WAV cases, including the waveform/difference view (M5/M6).
- The exact source/provenance and names of demo audio files, plus test output.
- A brief, honest AI-use note if AI was used, stating what it assisted with and
  how the resulting work was checked; the base application’s AI-assisted origin
  must also be disclosed in the team declaration/reflection.
