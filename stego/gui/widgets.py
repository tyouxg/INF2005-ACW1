"""Shared widgets: a media preview that shows images and plays audio."""

from pathlib import Path

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QPixmap
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtWidgets import (QFileDialog, QGroupBox, QHBoxLayout, QLabel, QLineEdit,
                               QPushButton, QVBoxLayout, QWidget)

from ..core import media


class MediaView(QGroupBox):
    """Preview box: scaled image for PNG/BMP, play/stop buttons for WAV."""

    def __init__(self, title: str):
        super().__init__(title)
        self.path = None
        self.image = QLabel("No file loaded")
        self.image.setAlignment(Qt.AlignCenter)
        self.image.setMinimumSize(280, 200)
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
            pix = QPixmap(str(path))
            self.image.setPixmap(pix.scaled(self.image.size(), Qt.KeepAspectRatio,
                                            Qt.SmoothTransformation))
        else:
            self._set_audio_controls(True)
            self.image.setPixmap(QPixmap())
            self.image.setText(f"♫  {self.path.name}")
            self.player.setSource(QUrl.fromLocalFile(str(path)))
        self.info.setText(f"{self.path.name}\n{cover.describe()}")

    def clear(self):
        self.player.stop()
        self.player.setSource(QUrl())
        self.path = None
        self.image.setPixmap(QPixmap())
        self.image.setText("No file loaded")
        self.info.setText("")
        self._set_audio_controls(False)


class FilePicker(QWidget):
    """Line edit + Browse button."""

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
        path, _ = QFileDialog.getOpenFileName(self, self.caption, self.edit.text(), self.filter)
        if path:
            self.edit.setText(path)

    def text(self) -> str:
        return self.edit.text().strip()
