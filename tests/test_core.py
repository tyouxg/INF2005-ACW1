import wave

import numpy as np
import pytest
from PIL import Image

from stego import messages
from stego.core import crypto, imagetools, lsb, media
from stego.core.protect import (AUTHENTIC, SIGNATURE_INVALID, TAMPERED, WRONG_START,
                                CapacityError, protect, verify)

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


def test_psnr_identical_is_infinite(png):
    cover = media.load_cover(png)
    assert imagetools.psnr(cover, cover.copy()) == float("inf")
    assert imagetools.changed_pixels(cover, cover.copy()) == 0


def test_psnr_drops_as_k_rises(png, tmp_path, keys):
    cover = media.load_cover(png)
    scores = [imagetools.psnr(cover, roundtrip(png, tmp_path, keys, k, messages.LONG)[0])
              for k in (1, 4, 8)]
    assert scores[0] > scores[1] > scores[2]


def test_diff_map_marks_only_changed_pixels(png, tmp_path, keys):
    cover = media.load_cover(png)
    stego, _ = roundtrip(png, tmp_path, keys, 8, messages.SHORT)
    arr = np.array(imagetools.diff_map(cover, stego))
    red = np.all(arr == (255, 0, 0), axis=2).sum()
    assert red == imagetools.changed_pixels(cover, stego) > 0


def test_jpeg_cover_saved_as_png_is_authentic(png, tmp_path, keys):
    jpg = tmp_path / "cover.jpg"
    Image.open(png).save(jpg, quality=90)
    cover = media.load_cover(jpg)
    stego, _, _ = protect(cover, jpg.name, messages.SHORT, 2, KEY, keys[0])
    out = tmp_path / "cover_stego.png"
    media.save_cover(stego, out)
    assert verify(media.load_cover(out), KEY, keys[1]).verdict == AUTHENTIC


def test_jpeg_recompression_destroys_payload(png, tmp_path, keys):
    stego, _ = roundtrip(png, tmp_path, keys, 2, messages.SHORT)
    recompressed = tmp_path / "recompressed.jpg"
    Image.fromarray(stego.data.reshape(120, 160, 3)).save(recompressed, quality=95)
    assert verify(media.load_cover(recompressed), KEY, keys[1]).verdict != AUTHENTIC
