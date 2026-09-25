import os

import numpy as np
import pytest

from stego.core import media, protect, visual
from tests.test_core import KEY, keys, png, wav  # noqa: F401  (fixtures)


@pytest.mark.parametrize("encrypt", [False, True])
@pytest.mark.parametrize("cover_file", ["png", "wav"])
@pytest.mark.parametrize("text", ["", "hi", "naïve café ✓ \"quoted\"\n" * 20])
def test_body_size_is_exact(request, keys, cover_file, text, encrypt):
    path = request.getfixturevalue(cover_file)
    cover = media.load_cover(path)
    _, _, info = protect.protect(cover, path.name, text, 2, KEY, keys[0], encrypt)
    assert protect.body_size(cover, path.name, text, 2, encrypt) == info["body_len"]


def test_body_size_matches_capacity_check(png, keys):
    # a message that exactly fills the cover must still be accepted
    cover = media.load_cover(png)
    cap = protect.capacity_bytes(cover, 1)
    overhead = protect.body_size(cover, png.name, "", 1)
    text = "x" * (cap - overhead)
    assert protect.body_size(cover, png.name, text, 1) == cap
    protect.protect(cover, png.name, text, 1, KEY, keys[0])
    with pytest.raises(protect.CapacityError):
        protect.protect(cover, png.name, text + "x", 1, KEY, keys[0])


def test_difference_marks_only_changed_pixels(png, keys):
    cover = media.load_cover(png)
    stego, _, info = protect.protect(cover, png.name, "hello", 1, KEY, keys[0])
    diff = visual.difference(cover, stego)
    assert diff.shape == (120, 160, 3)
    assert set(np.unique(diff)) <= {0, 255}      # k=1 changes are stretched to full white
    changed = visual.changed_pixels(cover, stego)
    assert 0 < changed <= info["units_used"]
    assert visual.difference(cover, cover).max() == 0


def test_lsb_plane(png):
    cover = media.load_cover(png)
    plane = visual.lsb_plane(cover)
    assert plane.shape == (120, 160, 3)
    assert np.array_equal(plane // 255, visual.image_rgb(cover) & 1)


@pytest.fixture(scope="module")
def qapp():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    widgets = pytest.importorskip("PySide6.QtWidgets")
    return widgets.QApplication.instance() or widgets.QApplication([])


def test_gui_smoke(qapp, png, tmp_path):
    from stego.gui.app import MainWindow
    win = MainWindow()
    s = win.sender
    s.priv_pick.edit.setText(str(tmp_path / "missing.pem"))
    assert not s.go.isEnabled()

    s.cover_pick.edit.setText(str(png))
    assert s.cover is not None
    s.stego_key.setText(KEY)
    assert not s.go.isEnabled()                   # still no private key
    assert "private key" in s.hint.text()

    s.msg.setPlainText("x" * 100_000)
    assert "DOES NOT FIT" in s.capacity.text()
    s.msg.setPlainText("hello")
    assert "used" in s.capacity.text()
    win.close()


def test_shrink_max_keeps_single_pixel():
    arr = np.zeros((301, 400, 3), dtype=np.uint8)
    arr[300, 399] = 255                            # lone changed pixel in the padded corner
    small = visual.shrink_max(arr, 4)
    assert small.shape == (76, 100, 3)
    assert small.max() == 255
