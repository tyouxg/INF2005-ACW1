"""Shared widgets: media previews, the difference view and a file picker."""

import math
from contextlib import contextmanager
from pathlib import Path

import numpy as np
from PySide6.QtCore import QSettings, Qt, QUrl
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtWidgets import (QApplication, QComboBox, QFileDialog, QGroupBox, QHBoxLayout,
                               QLabel, QLineEdit, QPushButton, QSizePolicy, QVBoxLayout,
                               QWidget)
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure

from ..core import media, visual


def _settings() -> QSettings:
    return QSettings("INF2005-ACW1", "StegoVerifier")


def last_dir() -> str:
    return _settings().value("last_dir", "", str)


def remember_dir(path) -> None:
    _settings().setValue("last_dir", str(Path(path).parent))


@contextmanager
def busy():
    """Wait cursor while scrypt and the embedding run."""
    QApplication.setOverrideCursor(Qt.WaitCursor)
    try:
        yield
    finally:
        QApplication.restoreOverrideCursor()


def array_to_pixmap(arr: np.ndarray) -> QPixmap:
    h, w = arr.shape[:2]
    if arr.ndim == 2:
        img = QImage(arr.data, w, h, w, QImage.Format_Grayscale8)
    else:
        img = QImage(arr.data, w, h, 3 * w, QImage.Format_RGB888)
    # QImage doesn't own the numpy buffer, so copy before arr goes away
    return QPixmap.fromImage(img.copy())


class ImageLabel(QLabel):
    """QLabel that keeps its pixmap scaled to fit when the window is resized."""

    def __init__(self, text: str = ""):
        super().__init__(text)
        self._pix = None
        self._arr = None
        self.setAlignment(Qt.AlignCenter)
        self.setMinimumSize(240, 140)
        self.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Ignored)

    def set_image(self, pix: QPixmap | None, text: str = ""):
        self._pix, self._arr = pix, None
        if pix is None:
            super().setPixmap(QPixmap())
            self.setText(text)
        else:
            self._rescale()

    def set_array(self, arr: np.ndarray, keep_bright: bool = False):
        """Show a numpy image. keep_bright shrinks with a max filter first so
        isolated bright pixels (changed pixels in the diff) stay visible."""
        self._arr, self._keep_bright = arr, keep_bright
        self._rescale()

    def _rescale(self):
        if self._arr is not None:
            arr = self._arr
            if self._keep_bright:
                f = math.ceil(max(arr.shape[0] / max(1, self.height()),
                                 arr.shape[1] / max(1, self.width())))
                if f > 1:
                    arr = visual.shrink_max(arr, f)
            # no smoothing: it would blur single-pixel detail into grey
            pix = array_to_pixmap(arr).scaled(self.size(), Qt.KeepAspectRatio,
                                              Qt.FastTransformation)
            super().setPixmap(pix)
        elif self._pix is not None:
            super().setPixmap(self._pix.scaled(self.size(), Qt.KeepAspectRatio,
                                               Qt.SmoothTransformation))

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._rescale()


class MediaView(QGroupBox):
    """Preview box: scaled image for PNG/BMP, play/stop buttons for WAV."""

    def __init__(self, title: str):
        super().__init__(title)
        self.path = None
        self.image = ImageLabel("No file loaded")
        self.info = QLabel("")
        self.info.setWordWrap(True)

        self.player = QMediaPlayer(self)
        self.audio_out = QAudioOutput(self)
        self.player.setAudioOutput(self.audio_out)
        self.play_btn = QPushButton("Play")
        self.stop_btn = QPushButton("Stop")
        self.play_btn.clicked.connect(self.player.play)
        self.stop_btn.clicked.connect(self.player.stop)
        controls = QHBoxLayout()
        controls.addWidget(self.play_btn)
        controls.addWidget(self.stop_btn)
        self._set_audio_controls(False)

        lay = QVBoxLayout(self)
        lay.addWidget(self.image, 1)
        lay.addLayout(controls)
        lay.addWidget(self.info)

    def _set_audio_controls(self, on: bool):
        self.play_btn.setVisible(on)
        self.stop_btn.setVisible(on)

    def show_file(self, path, cover=None):
        self.player.stop()
        # release the file handle, otherwise Windows won't let us overwrite it
        self.player.setSource(QUrl())
        self.path = Path(path)
        cover = cover or media.load_cover(path)
        if cover.kind == "image":
            self._set_audio_controls(False)
            self.image.set_image(QPixmap(str(path)))
        else:
            self._set_audio_controls(True)
            self.image.set_image(None, f"♫  {self.path.name}")
            self.player.setSource(QUrl.fromLocalFile(str(path)))
        self.info.setText(f"{self.path.name}\n{cover.describe()}")

    def clear(self):
        self.player.stop()
        self.player.setSource(QUrl())
        self.path = None
        self.image.set_image(None, "No file loaded")
        self.info.setText("")
        self._set_audio_controls(False)


class DiffView(QGroupBox):
    """Shows where the payload went: amplified |stego - cover|, LSB planes, or Histograms."""

    MODES = [
        "Amplified |stego − cover|", 
        "LSB plane of stego", 
        "LSB plane of cover",
        "Histogram of cover",
        "Histogram of stego"
    ]

    def __init__(self, title: str = "Difference"):
        super().__init__(title)
        self.cover = self.stego = None
        self.mode = QComboBox()
        self.mode.addItems(self.MODES)
        self.mode.currentIndexChanged.connect(self._render)
        self.save_btn = QPushButton("Save full size…")
        self.save_btn.setToolTip("Save this view at 1:1 scale, e.g. for the evidence folder")
        self.save_btn.clicked.connect(self._save)
        
        self.image = ImageLabel("Protect an image to see the difference")
        # Initialize the matplotlib widget and hide it by default
        self.histogram = HistogramView()
        self.histogram.setVisible(False)
        
        self.info = QLabel("")
        self.info.setWordWrap(True)
        self._arr = None

        top = QHBoxLayout()
        top.addWidget(self.mode, 1)
        top.addWidget(self.save_btn)
        lay = QVBoxLayout(self)
        lay.addLayout(top)
        
        # Add both to the layout; we will hide/show them dynamically
        lay.addWidget(self.image, 1)
        lay.addWidget(self.histogram, 1)
        lay.addWidget(self.info)

    def set_pair(self, cover, stego, k: int = 0):
        self.cover, self.stego, self.stego_k = cover, stego, k
        self._render()

    def clear(self):
        self.set_pair(None, None)

    def _render(self):
        c, s = self.cover, self.stego
        self.info.setText("")
        self._arr = None
        self.save_btn.setEnabled(False)
        
        if c is None or s is None:
            self.image.setVisible(True)
            self.histogram.setVisible(False)
            self.image.set_image(None, "Protect an image to see the difference")
            return
            
        if c.kind != "image":
            self.image.setVisible(True)
            self.histogram.setVisible(False)
            self.image.set_image(None, "Difference view is for images only")
            return
            
        mode = self.mode.currentIndex()
        
        # Modes 0, 1, 2 are standard image views
        if mode in [0, 1, 2]:
            self.histogram.setVisible(False)
            self.image.setVisible(True)
            if mode == 0:
                arr = visual.difference(c, s)
                n = visual.changed_pixels(c, s)
                total = c.params["width"] * c.params["height"]
                self.info.setText(f"{n:,} of {total:,} pixels changed ({100 * n / total:.2f}%). "
                                  "Black = unchanged.")
            else:
                arr = visual.lsb_plane(s if mode == 1 else c)
                self.info.setText("Bit 0 of every RGB byte. The payload looks like random noise. "
                                  "Save full size to see it properly.")
            self._arr = arr
            self.save_btn.setEnabled(True)
            self.image.set_array(arr, keep_bright=(mode == 0))
            
        # Modes 3 and 4 are the new histogram views
        elif mode == 3:
            self.image.setVisible(False)
            self.histogram.setVisible(True)
            self.info.setText("RGB intensity distribution of the original cover.")
            # Use the cover to set its own y-axis limits uniformly across all 3 colors
            c_rgb = visual.image_rgb(c)
            self.histogram.plot_image(c_rgb, ref_arr=c_rgb)
            
        elif mode == 4:
            self.image.setVisible(False)
            self.histogram.setVisible(True)
            self.info.setText("RGB intensity distribution of the stego image.")
            # Plot the stego array, but force it to use the cover's y-axis limits
            self.histogram.plot_image(visual.image_rgb(s), ref_arr=visual.image_rgb(c))

    def _save(self):
        # We disable the save button for histograms to keep it simple,
        # so this logic remains untouched for modes 0, 1, 2.
        name = ["diff", "lsb_stego", "lsb_cover", "", ""][self.mode.currentIndex()]
        start = str(Path(last_dir() or ".") / f"{name}_k{self.stego_k}.png")
        path, _ = QFileDialog.getSaveFileName(self, "Save view", start, "PNG image (*.png)")
        if path:
            if not Path(path).suffix:
                path += ".png"
            array_to_pixmap(self._arr).save(path)


class FilePicker(QWidget):
    """Line edit + Browse button. Browsing starts in the last folder used."""

    def __init__(self, caption: str, filter: str, default: str = ""):
        super().__init__()
        self.caption, self.filter = caption, filter
        self.edit = QLineEdit(default)
        btn = QPushButton("Browse…")
        btn.clicked.connect(self._browse)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self.edit, 1)
        lay.addWidget(btn)

    def _browse(self):
        start = self.text() if self.text() and Path(self.text()).exists() else last_dir()
        path, _ = QFileDialog.getOpenFileName(self, self.caption, start, self.filter)
        if path:
            remember_dir(path)
            self.edit.setText(path)

    def text(self) -> str:
        return self.edit.text().strip()

    def is_file(self) -> bool:
        return bool(self.text()) and Path(self.text()).is_file()

class HistogramView(QWidget):
    """A PySide6 widget that displays RGB pixel intensity histograms."""
    def __init__(self, title: str = "Statistical Steganalysis"):
        super().__init__()
        # Set up the Matplotlib figure and canvas to embed in PySide6
        self.figure = Figure(figsize=(8, 3))
        self.canvas = FigureCanvasQTAgg(self.figure)
        
        lay = QVBoxLayout(self)
        lay.addWidget(self.canvas)
        self.clear()

    def plot_image(self, arr: np.ndarray, ref_arr: np.ndarray = None):
        """Plots histograms. If ref_arr is provided, its maximum bin height is used to lock the y-axis."""
        self.figure.clear()
        colors = ('red', 'green', 'blue')
        
        # Find the highest peak in the reference array to lock the y-axis
        ymax = None
        if ref_arr is not None:
            max_counts = [np.histogram(ref_arr[:, :, i], bins=256, range=(0, 256))[0].max() for i in range(3)]
            ymax = max(max_counts) * 1.05  # Add 5% padding to the top so peaks don't touch the ceiling
            
        for i, color in enumerate(colors):
            ax = self.figure.add_subplot(1, 3, i + 1)
            channel_data = arr[:, :, i].ravel()
            ax.hist(channel_data, bins=256, range=(0, 256), color=color)
            ax.set_title(f"{color.capitalize()} Channel")
            ax.set_xlim([0, 255])
            
            # Lock the y-axis if a reference limit was calculated
            if ymax is not None:
                ax.set_ylim([0, ymax])
                
        self.figure.tight_layout()
        self.canvas.draw()

    def clear(self):
        self.figure.clear()
        self.canvas.draw()