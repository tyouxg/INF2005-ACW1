"""Shared widgets: media previews, the difference view and a file picker."""

import math
from contextlib import contextmanager
from pathlib import Path

import numpy as np
from PySide6.QtCore import QSettings, Qt, QUrl
from PySide6.QtGui import QColor, QDesktopServices, QImage, QPainter, QPen, QPixmap
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtWidgets import (QApplication, QComboBox, QFileDialog, QGroupBox, QHBoxLayout,
                               QLabel, QLineEdit, QPushButton, QSizePolicy, QSlider,
                               QVBoxLayout, QWidget)
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure

from ..core import imagetools, media, visual


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
    """Preview box: scaled image for PNG/BMP, play/stop for WAV, frame slider for video."""

    def __init__(self, title: str):
        super().__init__(title)
        self.path = None
        self._video = None
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

        # video: step through the frames here, or open the file in a real player
        # (FFV1 plays in VLC and ffplay, not in Windows' built-in app)
        self.frame = QSlider(Qt.Horizontal)
        self.frame.valueChanged.connect(self._show_frame)
        self.open_btn = QPushButton("Open in video player")
        self.open_btn.clicked.connect(
            lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.path))))
        self._set_audio_controls(False)
        self._set_video_controls(False)

        lay = QVBoxLayout(self)
        lay.addWidget(self.image, 1)
        lay.addLayout(controls)
        lay.addWidget(self.frame)
        lay.addWidget(self.open_btn)
        lay.addWidget(self.info)

    def _set_audio_controls(self, on: bool):
        self.play_btn.setVisible(on)
        self.stop_btn.setVisible(on)

    def _set_video_controls(self, on: bool):
        self.frame.setVisible(on)
        self.open_btn.setVisible(on)

    def _show_frame(self, i: int):
        if self._video is not None:
            self.image.set_image(array_to_pixmap(media.video_frame(self._video, i)))
            self.image.setToolTip(f"Frame {i + 1} of {self._video.params['frames']}")

    def _waveform_pixmap(self, cover):
        """Draw a small before/after WAV waveform without another dependency."""
        width, height = 420, 150
        pix = QPixmap(width, height)
        pix.fill(QColor("#f5f7fa"))
        painter = QPainter(pix)
        try:
            painter.setPen(QPen(QColor("#c4cbd4"), 1))
            middle = height // 2
            painter.drawLine(10, middle, width - 10, middle)
            lows, highs = media.audio_waveform(cover, width - 20)
            painter.setPen(QPen(QColor("#1565c0"), 1))
            scale = (height - 24) / 2
            for i, (low, high) in enumerate(zip(lows, highs, strict=True)):
                x = 10 + round(i * (width - 20) / max(1, len(lows) - 1))
                y_low = middle - round(max(-1.0, min(1.0, low)) * scale)
                y_high = middle - round(max(-1.0, min(1.0, high)) * scale)
                painter.drawLine(x, y_low, x, y_high)
        finally:
            painter.end()
        return pix

    def show_file(self, path, cover=None):
        self.player.stop()
        # release the file handle, otherwise Windows won't let us overwrite it
        self.player.setSource(QUrl())
        self.path = Path(path)
        cover = cover or media.load_cover(path)
        self._video = None
        self._set_video_controls(cover.kind == "video")
        if cover.kind == "image":
            self._set_audio_controls(False)
            self.image.set_image(QPixmap(str(path)))
            self.image.setToolTip("")
        elif cover.kind == "video":
            self._set_audio_controls(False)
            self._video = cover
            self.frame.setRange(0, cover.params["frames"] - 1)
            self.frame.setValue(0)
            self._show_frame(0)
        else:
            self._set_audio_controls(True)
            self.image.set_image(self._waveform_pixmap(cover))
            self.image.setToolTip("Waveform: average amplitude across channels")
            self.player.setSource(QUrl.fromLocalFile(str(path)))
        suffix = "\nWaveform: average amplitude across channels" if cover.kind == "audio" else ""
        self.info.setText(f"{self.path.name}\n{cover.describe()}{suffix}")

    def clear(self):
        self.player.stop()
        self.player.setSource(QUrl())
        self.path = None
        self._video = None
        self.image.set_image(None, "No file loaded")
        self.image.setToolTip("")
        self.info.setText("")
        self._set_audio_controls(False)
        self._set_video_controls(False)


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
            
        prefix = ""
        if c.kind == "video":
            # show the one frame the key-derived start landed in
            f = visual.first_changed_frame(c, s)
            prefix = f"Frame {f + 1} of {c.params['frames']} (picked by the stego key). "
            c, s = visual.frame_cover(c, f), visual.frame_cover(s, f)
        elif c.kind != "image":
            self.image.setVisible(True)
            self.histogram.setVisible(False)
            self.image.set_image(None, "Difference view is for images and video only")
            return
            
        mode = self.mode.currentIndex()
        
        # Modes 0, 1, 2 are standard image views
        if mode in [0, 1, 2]:
            self.histogram.setVisible(False)
            self.image.setVisible(True)
            if mode == 0:
                arr = visual.difference(c, s)
                q = imagetools.compare(c, s)
                self.info.setText(f"{q['changed_pixels']:,} of {q['total_pixels']:,} pixels changed "
                                  f"({q['percent_changed']:.2f}%). PSNR {q['psnr_db']:.1f} dB, "
                                  f"MSE {q['mse']:.4f}. Black = unchanged.")
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

        if prefix:
            self.info.setText(prefix + self.info.text())

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
        """Plots histograms, ignoring solid background spikes (0 and 255) to zoom in on image data."""
        self.figure.clear()
        colors = ('red', 'green', 'blue')
        
        target = ref_arr if ref_arr is not None else arr
        
        channel_ymax = []
        for i in range(3):
            counts = np.histogram(target[:, :, i], bins=256, range=(0, 256))[0]
            # Exclude extreme saturated values (0 = pure black, 255 = pure white)
            interior_counts = counts[1:255]
            if len(interior_counts) > 0 and interior_counts.max() > 0:
                peak = float(interior_counts.max())
            else:
                peak = float(counts.max())
            channel_ymax.append(max(1.0, peak * 1.15))
            
        for i, color in enumerate(colors):
            ax = self.figure.add_subplot(1, 3, i + 1)
            channel_data = arr[:, :, i].ravel()
            ax.hist(channel_data, bins=256, range=(0, 256), color=color)
            ax.set_title(f"{color.capitalize()} Channel")
            ax.set_xlim([0, 255])
            ax.set_ylim([0, channel_ymax[i]])
                
        self.figure.tight_layout()
        self.canvas.draw()

    def clear(self):
        self.figure.clear()
        self.canvas.draw()