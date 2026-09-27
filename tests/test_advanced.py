"""Tests for the optional challenges: robust mode, masked body (v2), steganalysis, video."""

import numpy as np
import pytest

from stego import messages
from stego.core import attacks, media, payload, protect, robust, steganalysis
# isolated_replay_store is autouse: importing it keeps these tests off the real
# keys/seen_nonces.json, otherwise demo files would later say "Replay Detected"
from tests.test_core import KEY, isolated_replay_store, keys, png, wav  # noqa: F401  (fixtures)


# --- robust mode ---

def test_vote_fixes_a_minority_of_bad_copies():
    data = b"robust!"
    spread = bytearray(robust.spread(data, 5))
    spread[0] ^= 0xFF              # wreck copy 1's first byte
    spread[len(data) + 3] ^= 0x0F  # and part of copy 2
    assert robust.vote(bytes(spread), len(data), 5) == data


def test_header_carries_reps_and_old_headers_still_parse():
    hdr = payload.unpack_header(payload.pack_header(3, 1234, reps=5))
    assert (hdr.version, hdr.k, hdr.reps, hdr.body_len) == (payload.VERSION, 3, 5, 1234)
    old = payload.unpack_header(payload.pack_header(2, 99, version=1))
    assert (old.version, old.reps) == (1, 1)


@pytest.mark.parametrize("reps", [3, 5])
def test_robust_roundtrip(png, keys, reps):
    stego, _, info = protect.protect(media.load_cover(png), "c.png", messages.SHORT, 2, KEY, keys[0], reps=reps)
    res = protect.verify(stego, KEY, keys[1])
    assert res.verdict == protect.AUTHENTIC and res.message == messages.SHORT
    assert res.details["reps"] == reps and info["reps"] == reps


def test_robust_capacity_is_divided_by_reps(png):
    cover = media.load_cover(png)
    assert protect.capacity_bytes(cover, 2, 5) < protect.capacity_bytes(cover, 2) // 5 + 1


@pytest.mark.parametrize("cover_file", ["png", "wav"])
def test_robust_file_survives_what_breaks_a_normal_one(request, keys, cover_file):
    cover = media.load_cover(request.getfixturevalue(cover_file))
    for reps in (1, 5):
        stego, _, _ = protect.protect(cover, "x", messages.SHORT, 2, KEY, keys[0], reps=reps)
        rows = {r.name: r for r in attacks.run_all(stego, KEY, keys[1])}
        assert all(r.passed for r in rows.values()), [(r.name, r.got) for r in rows.values() if not r.passed]
        for name in ("Flip one payload bit", "Mild LSB noise", "Scratch over payload"):
            assert rows[name].recovered == (reps > 1), name


# --- masked body (v2) and steganalysis ---

def test_old_v1_files_still_verify(png, keys):
    stego, _, _ = protect.protect(media.load_cover(png), "c.png", messages.SHORT, 2, KEY, keys[0], version=1)
    res = protect.verify(stego, KEY, keys[1])
    assert res.verdict == protect.AUTHENTIC and res.details["version"] == 1


@pytest.mark.parametrize("k", [1, 2, 8])
def test_scan_reads_a_v1_payload_without_the_key(png, keys, k):
    cover = media.load_cover(png)
    stego, _, info = protect.protect(cover, "c.png", messages.SHORT, k, KEY, keys[0], version=1)
    found = steganalysis.scan(stego)
    assert found.found and found.k == k
    assert '"media_hash"' in found.text and messages.SHORT[:30] in found.text
    assert info["start"] <= found.start <= info["start"] + info["units_used"]


@pytest.mark.parametrize("k", [1, 2, 8])
def test_scan_finds_nothing_in_v2_or_a_clean_cover(png, keys, k):
    cover = media.load_cover(png)
    stego, _, _ = protect.protect(cover, "c.png", messages.SHORT, k, KEY, keys[0])
    assert not steganalysis.scan(stego).found
    assert not steganalysis.scan(cover).found


# --- video ---

@pytest.fixture
def mkv(tmp_path):
    rng = np.random.default_rng(5)
    frames = rng.integers(0, 256, (8, 45, 61, 3), dtype=np.uint8)     # odd sizes on purpose
    cover = media.Cover("video", frames.reshape(-1).copy(), 1,
                        {"width": 61, "height": 45, "frames": 8, "fps": 12.5})
    path = tmp_path / "cover.mkv"
    media.save_cover(cover, path)
    return path


def test_video_roundtrip_is_lossless(mkv, tmp_path):
    cover = media.load_cover(mkv)
    assert cover.params == {"width": 61, "height": 45, "frames": 8, "fps": 12.5}
    media.save_cover(cover, tmp_path / "again.mkv")
    assert np.array_equal(media.load_cover(tmp_path / "again.mkv").data, cover.data)


@pytest.mark.parametrize("k", [1, 8])
def test_video_authentic_after_save(mkv, tmp_path, keys, k):
    stego, _, _ = protect.protect(media.load_cover(mkv), mkv.name, messages.LONG, k, KEY, keys[0])
    out = tmp_path / "stego.mkv"
    media.save_cover(stego, out)
    res = protect.verify(media.load_cover(out), KEY, keys[1])
    assert res.verdict == protect.AUTHENTIC and res.message == messages.LONG


def test_video_attacks_all_caught(mkv, keys):
    stego, _, _ = protect.protect(media.load_cover(mkv), mkv.name, messages.SHORT, 2, KEY, keys[0])
    for r in attacks.run_all(stego, KEY, keys[1]):
        assert r.passed, f"{r.name}: expected {r.expected}, got {r.got}"


def test_video_lossy_output_refused(mkv):
    with pytest.raises(media.UnsupportedMedia):
        media.save_cover(media.load_cover(mkv), "out.mp4")
