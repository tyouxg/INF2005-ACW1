# M2 audio demo assets

Generate these files from the repository root with:

```powershell
.\.venv\Scripts\python tools\generate_audio_samples.py
```

The generator makes an original, synthetic 8-second 44.1 kHz stereo 16-bit
PCM cover and a long-message stego version at `k = 2`. It generates a temporary
signing key in memory and writes only `demo_public_key.pem`.

| File | Purpose |
| --- | --- |
| `cover_stereo_music.wav` | Cover used for the M2 positive demo. |
| `stego_long_message.wav` | Positive long-message audio case; verify with `demo_public_key.pem`. |
| `tampered_amplified_section.wav` | Same-length negative case. A 0.5-second section outside the embedded region was amplified, so verification must return **Tampered**. |
| `generation-details.json` | Exact sample format, demo stego key and amplified-section timing. |

The listed stego key is a coursework-demo shared secret, not a real secret.
Do not commit a private signing key. To demonstrate the exact manual workflow
requested in the workload notes, open `stego_long_message.wav` in Audacity,
amplify the first 0.5 seconds (the clear section identified in
`generation-details.json`), export as PCM WAV, and verify it as **Tampered**.
Trimming changes the carrier length and therefore normally produces **Wrong
Start Location** instead.

Quick verification commands:

```powershell
.\.venv\Scripts\python -m stego.cli verify samples\audio\stego_long_message.wav --key m2-audio-demo-key --pub samples\audio\demo_public_key.pem
.\.venv\Scripts\python -m stego.cli verify samples\audio\tampered_amplified_section.wav --key m2-audio-demo-key --pub samples\audio\demo_public_key.pem
```

These are synthetic tone-based test assets, not recordings. Add separately
licensed or team-recorded speech and music WAVs to the format-results evidence
before the final demo.
