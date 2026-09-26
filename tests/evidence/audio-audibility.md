# M2 audibility evidence

The code can calculate/display the waveform, but it cannot truthfully claim a
human listening result. The entries below record M2's initial listening test;
the listener/output device was not recorded, so repeat the comparison on the
demo laptop and add those details before submission.

| Cover and playback setup | k | Listener/result | Audible artefact or limitation |
| --- | ---: | --- | --- |
| `cover_stereo_music_stego_k1.wav`, 16-bit stereo, device not recorded | 1 | No discernible difference compared with `cover_stereo_music.wav` | Consistent with the lowest disturbance. |
| `cover_stereo_music_stego_k4.wav`, 16-bit stereo, device not recorded | 4 | Slight disruption around 1 s at maximum volume | More disturbance than `k = 1`. |
| `cover_stereo_music_stego_k8.wav`, 16-bit stereo, device not recorded | 8 | Noticeable disruption around 1 s at maximum volume | The low byte is completely replaced; this is the most audible/detectable tested 16-bit case. |
| `cover_stero_music_8bit_stego_k1.wav`, 8-bit stereo, device not recorded | 1 | Noticeable disruption | A one-bit change is proportionally larger in 8-bit PCM than 16-bit PCM. |
| `cover_stero_music_8bit_stego_k4.wav`, 8-bit stereo, device not recorded | 4 | Noticeable disruption | Four of the eight sample bits are replaced. |
| `cover_stero_music_8bit_stego_k8.wav`, 8-bit stereo, device not recorded | 8 | Noticeable disruption, more obvious at higher LSB use | Entire sample is replaced; do not claim transparency. |

Report these results as a limitation: higher `k` increases capacity but also
increases distortion and steganalysis risk. Lossy transcoding/re-encoding
(MP3/AAC/OGG) is out of scope because it can destroy LSB payload bits.
