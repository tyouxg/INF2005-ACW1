import wave

import numpy as np
import pytest
from PIL import Image

from stego import messages
from stego.core import crypto, lsb, media
from stego.core.protect import (AUTHENTIC, SIGNATURE_INVALID, TAMPERED, WRONG_START,
                                CapacityError, capacity_bytes, protect, verify)

KEY = "correct horse battery staple"


@pytest.fixture(scope="module")
def keys():
    priv = crypto.generate_keypair()
    return priv, priv.public_key()


@pytest.fixture
def png(tmp_path):
    rng = np.random.default_rng(1)
    arr = rng.integers(0, 256, (120, 160, 3), dtype=np.uint8)
    path = tmp_path / "cover.png"
    Image.fromarray(arr).save(path)
    return path


@pytest.fixture
def wav(tmp_path):
    t = np.arange(44100 * 2) / 44100
    samples = (8000 * np.sin(2 * np.pi * 440 * t)).astype("<i2")
    path = tmp_path / "cover.wav"
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(44100)
        w.writeframes(samples.tobytes())
    return path


def write_pcm_wav(path, channels, sampwidth, framerate=44100, seconds=2):
    """Create a deterministic PCM tone for format-level audio tests."""
    frames = int(framerate * seconds)
    t = np.arange(frames) / framerate
    signals = []
    for channel in range(channels):
        signals.append(0.45 * np.sin(2 * np.pi * (330 + channel * 110) * t))
    values = np.column_stack(signals)

    if sampwidth == 1:
        raw = np.clip(np.round((values + 1) * 127.5), 0, 255).astype(np.uint8)
        data = raw.tobytes()
    elif sampwidth == 2:
        raw = np.round(values * ((1 << 15) - 1)).astype("<i2")
        data = raw.tobytes()
    elif sampwidth == 3:
        integers = np.round(values * ((1 << 23) - 1)).astype(np.int32).reshape(-1)
        unsigned = integers & 0xFFFFFF
        raw = np.column_stack((unsigned & 0xFF, (unsigned >> 8) & 0xFF,
                               (unsigned >> 16) & 0xFF)).astype(np.uint8)
        data = raw.tobytes()
    else:
        raise ValueError("test helper supports 8-, 16-, and 24-bit PCM only")

    with wave.open(str(path), "wb") as w:
        w.setnchannels(channels)
        w.setsampwidth(sampwidth)
        w.setframerate(framerate)
        w.writeframes(data)


@pytest.fixture(params=[(1, 1), (2, 1), (1, 2), (2, 2), (1, 3), (2, 3)])
def pcm_wav(tmp_path, request):
    channels, sampwidth = request.param
    path = tmp_path / f"{channels}ch_{sampwidth * 8}bit.wav"
    write_pcm_wav(path, channels, sampwidth)
    return path, channels, sampwidth


def roundtrip(path, tmp_path, keys, k, text, **kw):
    priv, pub = keys
    cover = media.load_cover(path)
    stego, _, info = protect(cover, path.name, text, k, KEY, priv, **kw)
    out = tmp_path / ("stego" + path.suffix)
    media.save_cover(stego, out)
    return media.load_cover(out), info


def test_lsb_roundtrip_wraps_around():
    carrier = np.zeros(100, dtype=np.uint8)
    data = b"wrap test!"
    lsb.embed(carrier, data, 95, 3)
    assert lsb.extract(carrier, 95, len(data), 3) == data


@pytest.mark.parametrize("k", range(1, 9))
def test_image_authentic_all_k(png, tmp_path, keys, k):
    stego, _ = roundtrip(png, tmp_path, keys, k, messages.SHORT)
    res = verify(stego, KEY, keys[1])
    assert res.verdict == AUTHENTIC
    assert res.message == messages.SHORT


@pytest.mark.parametrize("k", [1, 4, 8])
def test_audio_authentic(wav, tmp_path, keys, k):
    stego, _ = roundtrip(wav, tmp_path, keys, k, messages.LONG)
    res = verify(stego, KEY, keys[1])
    assert res.verdict == AUTHENTIC
    assert res.message == messages.LONG


def test_audio_high_byte_untouched(wav, tmp_path, keys):
    cover = media.load_cover(wav)
    stego, _ = roundtrip(wav, tmp_path, keys, 8, messages.LONG)
    assert np.array_equal(cover.data[1::2], stego.data[1::2])


def test_audio_formats_roundtrip_and_preserve_non_carrier_bytes(pcm_wav, tmp_path, keys):
    path, channels, sampwidth = pcm_wav
    cover = media.load_cover(path)
    stego, _ = roundtrip(path, tmp_path, keys, 2, messages.SHORT)

    assert verify(stego, KEY, keys[1]).verdict == AUTHENTIC
    assert stego.params == cover.params
    assert len(stego.carrier) == cover.params["nframes"] * channels
    if sampwidth > 1:
        non_carrier = np.arange(len(cover.data)) % sampwidth != 0
        assert np.array_equal(cover.data[non_carrier], stego.data[non_carrier])


@pytest.mark.parametrize("sampwidth", [1, 2, 3])
def test_audio_waveform_is_normalised_for_pcm_widths(tmp_path, sampwidth):
    path = tmp_path / f"waveform_{sampwidth}.wav"
    write_pcm_wav(path, channels=2, sampwidth=sampwidth, seconds=0.1)
    lows, highs = media.audio_waveform(media.load_cover(path), points=20)
    assert len(lows) == len(highs) == 20
    assert np.all(lows <= highs)
    assert np.all(lows >= -1.01)
    assert np.all(highs <= 1.01)


def test_stereo_ten_second_capacity_at_two_lsbs(tmp_path):
    path = tmp_path / "ten_seconds_stereo.wav"
    write_pcm_wav(path, channels=2, sampwidth=2, seconds=10)
    cover = media.load_cover(path)
    assert len(cover.carrier) == 10 * 44_100 * 2
    assert capacity_bytes(cover, 2) == 220_484


def test_encrypted_message(png, tmp_path, keys):
    stego, _ = roundtrip(png, tmp_path, keys, 2, messages.CUSTOM, encrypt_message=True)
    res = verify(stego, KEY, keys[1])
    assert res.verdict == AUTHENTIC
    assert res.message == messages.CUSTOM
    assert messages.CUSTOM not in str(res.payload)


def test_wrong_key_gives_wrong_start(png, tmp_path, keys):
    stego, _ = roundtrip(png, tmp_path, keys, 2, messages.SHORT)
    assert verify(stego, "wrong key", keys[1]).verdict == WRONG_START


def test_wrong_start_offset(png, tmp_path, keys):
    stego, info = roundtrip(png, tmp_path, keys, 2, messages.SHORT)
    res = verify(stego, KEY, keys[1], start_override=info["start"] + 7)
    assert res.verdict == WRONG_START


def test_wrong_public_key(wav, tmp_path, keys):
    stego, _ = roundtrip(wav, tmp_path, keys, 2, messages.SHORT)
    other = crypto.generate_keypair().public_key()
    assert verify(stego, KEY, other).verdict == SIGNATURE_INVALID


def test_tampered_outside_payload(png, tmp_path, keys):
    stego, info = roundtrip(png, tmp_path, keys, 1, messages.SHORT)
    # flip a pixel far away from where the payload sits
    far = (info["start"] + info["carrier_units"] // 2) % info["carrier_units"]
    stego.carrier[far] ^= 0x80
    assert verify(stego, KEY, keys[1]).verdict == TAMPERED


def test_tampered_audio_upper_bits_in_region(wav, tmp_path, keys):
    stego, info = roundtrip(wav, tmp_path, keys, 1, messages.SHORT)
    i = (info["start"] + 100) % info["carrier_units"]
    stego.data[1::2][i] ^= 0x10   # high byte of a sample inside the payload region
    assert verify(stego, KEY, keys[1]).verdict == TAMPERED


def test_payload_bits_corrupted(png, tmp_path, keys):
    stego, info = roundtrip(png, tmp_path, keys, 1, messages.SHORT)
    idx = (info["start"] + 64 + 200) % info["carrier_units"]
    stego.carrier[idx] ^= 1
    assert verify(stego, KEY, keys[1]).verdict == SIGNATURE_INVALID


def test_capacity_check(tmp_path, keys):
    path = tmp_path / "tiny.png"
    Image.fromarray(np.zeros((8, 8, 3), dtype=np.uint8)).save(path)
    with pytest.raises(CapacityError):
        protect(media.load_cover(path), "tiny.png", messages.LONG, 1, KEY, keys[0])


def test_jpeg_output_refused(png, keys):
    cover = media.load_cover(png)
    with pytest.raises(media.UnsupportedMedia):
        media.save_cover(cover, "out.jpg")
