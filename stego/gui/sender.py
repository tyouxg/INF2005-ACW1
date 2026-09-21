"""Sender (party A): pick a cover, write a message, embed a signed payload."""

import json
from pathlib import Path

from PySide6.QtWidgets import (QCheckBox, QComboBox, QFileDialog, QFormLayout, QHBoxLayout,
                               QLabel, QLineEdit, QMessageBox, QPlainTextEdit, QPushButton,
                               QSpinBox, QVBoxLayout, QWidget)

from .. import messages
from ..core import crypto, media, protect
from .widgets import FilePicker, MediaView

MEDIA_FILTER = "Cover files (*.png *.bmp *.wav);;Images (*.png *.bmp);;Audio (*.wav)"


class SenderTab(QWidget):
    def __init__(self, keys_dir: Path):
        super().__init__()
        self.cover = None

        self.cover_pick = FilePicker("Choose cover", MEDIA_FILTER)
        self.cover_pick.edit.textChanged.connect(self.load_cover)

        self.preset = QComboBox()
        self.preset.addItems(["(type your own)", *messages.PRESETS])
        self.preset.currentTextChanged.connect(self._apply_preset)
        load_txt = QPushButton("Load .txt…")
        load_txt.clicked.connect(self._load_text_file)
        self.msg = QPlainTextEdit()
        self.msg.setPlaceholderText("Message to hide")
        self.msg.textChanged.connect(self._update_capacity)
        msg_row = QHBoxLayout()
        msg_row.addWidget(self.preset, 1)
        msg_row.addWidget(load_txt)

        self.k = QSpinBox()
        self.k.setRange(1, 8)
        self.k.valueChanged.connect(self._update_capacity)
        self.capacity = QLabel("")

        self.stego_key = QLineEdit()
        self.stego_key.setEchoMode(QLineEdit.Password)
        self.stego_key.setPlaceholderText("Shared secret with the receiver")
        self.encrypt = QCheckBox("Encrypt message (AES-GCM) for confidentiality")
        self.priv_pick = FilePicker("Private key", "PEM (*.pem)", str(keys_dir / "private_key.pem"))

        go = QPushButton("Protect && save stego file…")
        go.clicked.connect(self.run_protect)

        form = QFormLayout()
        form.addRow("Cover file", self.cover_pick)
        form.addRow("Preset", msg_row)
        form.addRow("Message", self.msg)
        form.addRow("LSBs used", self.k)
        form.addRow("", self.capacity)
        form.addRow("Stego key", self.stego_key)
        form.addRow("", self.encrypt)
        form.addRow("Private key", self.priv_pick)
        form.addRow("", go)

        self.cover_view = MediaView("Cover (before)")
        self.stego_view = MediaView("Stego (after)")
        views = QHBoxLayout()
        views.addWidget(self.cover_view)
        views.addWidget(self.stego_view)

        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumHeight(160)

        lay = QVBoxLayout(self)
        lay.addLayout(form)
        lay.addLayout(views, 1)
        lay.addWidget(self.log)

    def _apply_preset(self, name):
        if name in messages.PRESETS:
            self.msg.setPlainText(messages.PRESETS[name])
            self.encrypt.setChecked(name == "Custom")

    def _load_text_file(self):
        path, _ = QFileDialog.getOpenFileName(self, "Message file", "", "Text (*.txt)")
        if path:
            self.msg.setPlainText(Path(path).read_text(encoding="utf-8"))

    def load_cover(self, path):
        self.cover = None
        self.stego_view.clear()
        if not Path(path).is_file():
            self.cover_view.clear()
            return
        try:
            self.cover = media.load_cover(path)
            self.cover_view.show_file(path, self.cover)
        except Exception as e:
            self.cover_view.clear()
            self.log.setPlainText(f"Can't load cover: {e}")
        self._update_capacity()

    def _update_capacity(self):
        if self.cover is None:
            self.capacity.setText("")
            return
        cap = protect.capacity_bytes(self.cover, self.k.value())
        msg_len = len(self.msg.toPlainText().encode("utf-8"))
        # payload JSON + signature adds roughly 400 bytes on top of the message
        self.capacity.setText(f"Capacity ≈ {cap:,} bytes at {self.k.value()} LSB(s); "
                              f"message is {msg_len:,} bytes (+ ~400 bytes overhead)")

    def run_protect(self):
        if self.cover is None:
            QMessageBox.warning(self, "No cover", "Choose a cover image or WAV file first.")
            return
        cover_path = Path(self.cover_pick.text())
        try:
            priv = crypto.load_private_key(self.priv_pick.text())
        except Exception as e:
            QMessageBox.warning(self, "Private key", f"Couldn't load private key:\n{e}\n\n"
                                "Generate one in the Keys tab.")
            return

        try:
            stego, payload, info = protect.protect(
                self.cover, cover_path.name, self.msg.toPlainText(), self.k.value(),
                self.stego_key.text(), priv, self.encrypt.isChecked())
        except protect.CapacityError as e:
            QMessageBox.critical(self, "Capacity check failed", str(e))
            self.log.setPlainText(f"CAPACITY CHECK FAILED\n{e}")
            return
        except ValueError as e:
            QMessageBox.warning(self, "Can't protect", str(e))
            return

        suggested = cover_path.with_name(f"{cover_path.stem}_stego{cover_path.suffix}")
        ext = "*.wav" if self.cover.kind == "audio" else "*.png *.bmp"
        out, _ = QFileDialog.getSaveFileName(self, "Save stego file", str(suggested), f"({ext})")
        if not out:
            return
        try:
            media.save_cover(stego, out)
        except Exception as e:
            QMessageBox.critical(self, "Save failed", str(e))
            return

        self.stego_view.show_file(out)
        self.log.setPlainText(
            f"Saved {out}\n"
            f"Start offset {info['start']:,} of {info['carrier_units']:,} carrier bytes, "
            f"{info['k']} LSB(s), {info['body_len']:,} byte body, "
            f"{info['percent_used']:.2f}% of carrier used\n\n"
            + json.dumps(payload, indent=2))
