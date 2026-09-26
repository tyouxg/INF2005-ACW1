# M2 audio format results

## Automated compatibility coverage

`tests/test_core.py` now generates deterministic PCM tones and verifies a
protect -> save -> reload -> verify round trip for each row at `k = 2`.

| Channels | Width | Carrier selection verified | Expected result |
| --- | --- | --- | --- |
| Mono | 8-bit PCM | Every sample is a carrier byte | Authentic |
| Stereo | 8-bit PCM | Every interleaved sample is a carrier byte | Authentic |
| Mono | 16-bit PCM | First/little-endian byte only | Authentic |
| Stereo | 16-bit PCM | First byte of each interleaved sample only | Authentic |
| Mono | 24-bit PCM | First/little-endian byte only | Authentic |
| Stereo | 24-bit PCM | First byte of each interleaved sample only | Authentic |

The test also confirms that all non-carrier bytes are unchanged for 16- and
24-bit input, and that a 10-second 44.1 kHz stereo file has 882,000 carrier
bytes and 220,484 bytes of body capacity at `k = 2`.

## Real-file validation still required before the demo

No externally recorded speech/music assets were supplied with this repository,
so do not represent synthetic test coverage as a real-recording result. The
two completed GUI rows below use the generated tone-based cover; its 8-bit
version was exported locally from that same cover. M2 must still complete the
speech/music and demo-laptop checks before submission.

| Input | Source/provenance | Format | Protect/save/reload/verify | Playback | Notes |
| --- | --- | --- | --- | --- | --- |
| Speech WAV | Pending team recording/licensed source | Pending | Pending | Pending | Use PCM WAV. |
| Music WAV | Pending team recording/licensed source | Pending | Pending | Pending | Use PCM WAV. |
| Stereo WAV | `cover_stereo_music.wav` (generated) | Stereo, 16-bit, 44.1 kHz | GUI protect/save/reload tested at `k = 1`, `4`, `8`; matching stego outputs are present. Record the **Authentic** screenshot/verdict if not already captured. | Listening comparison completed; device/demo-laptop check pending | Synthetic tone-based asset. |
| 24-bit WAV | Automated fixture | Mono/stereo, 24-bit PCM | Pass in automated test | Pending real-file check | Add external file before final demo. |
| 8-bit WAV | `cover_stero_music_8bit.wav` (locally converted from generated cover) | Stereo, 8-bit, 44.1 kHz | GUI protect/save/reload tested at `k = 1`, `4`, `8`; matching stego outputs are present. Record the **Authentic** screenshot/verdict if not already captured. | Listening comparison completed; device/demo-laptop check pending | `k = 8` replaces the whole sample; initial listening result reports disruption at every tested `k`, increasing at higher `k`. |
