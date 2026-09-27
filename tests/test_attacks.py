import pytest

from stego import messages
from stego.core import attacks, media, protect, replay
from tests.test_core import KEY, keys, png, wav  # noqa: F401  (fixtures)


def make_stego(path, keys, k=2):
    cover = media.load_cover(path)
    stego, _, _ = protect.protect(cover, path.name, messages.SHORT, k, KEY, keys[0])
    return stego


# k=1 and k=8 are the edge cases, on both cover types
@pytest.mark.parametrize("k", [1, 2, 8])
@pytest.mark.parametrize("cover_file", ["png", "wav"])
def test_every_attack_is_caught(request, keys, cover_file, k):
    stego = make_stego(request.getfixturevalue(cover_file), keys, k)
    for r in attacks.run_all(stego, KEY, keys[1]):
        assert r.passed, f"{r.name}: expected {r.expected}, got {r.got} ({r.reason})"


def test_real_replay_store_untouched(png, keys, tmp_path, monkeypatch):
    real = tmp_path / "real_store.json"
    monkeypatch.setattr(replay, "DEFAULT_STORE", real)
    attacks.run_all(make_stego(png, keys), KEY, keys[1])
    assert not real.exists()
    assert replay.DEFAULT_STORE == real    # put back afterwards


def test_needs_an_authentic_file(png, keys):
    with pytest.raises(ValueError):
        attacks.run_all(media.load_cover(png), KEY, keys[1])
