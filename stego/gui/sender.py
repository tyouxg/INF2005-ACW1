"""Sender (party A): pick a cover, write a message, embed a signed payload."""

import json
from pathlib import Path

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (QCheckBox, QComboBox, QFileDialog, QFormLayout, QHBoxLayout,
                               QLabel, QLineEdit, QMessageBox, QPlainTextEdit, QPushButton,
                               QSpinBox, QVBoxLayout, QWidget)

from .. import messages
from ..core import crypto, media, protect
from .widgets import DiffView, FilePicker, MediaView, busy, last_dir, remember_dir

MEDIA_FILTER = "Cover files (*.png *.bmp *.wav);;Images (*.png *.bmp);;Audio (*.wav)"
OK_COLOUR, BAD_COLOUR = "#1b7f3b", "#b3261e"


class SenderTab(QWidget):
    saved = Signal(str)   # path of a newly written stego file

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
        self.msg.setMaximumHeight(110)
        self.msg.textChanged.connect(self._update_capacity)
        msg_row = QHBoxLayout()
        msg_row.addWidget(self.preset, 1)
        msg_row.addWidget(load_txt)

        self.k = QSpinBox()
        self.k.setRange(1, 8)
        self.k.valueChanged.connect(self._update_capacity)
        self.capacity = QLabel("")
        self.capacity.setWordWrap(True)

        self.stego_key = QLineEdit()
        self.stego_key.setEchoMode(QLineEdit.Password)
        self.stego_key.setPlaceholderText("Shared secret with the receiver")
        self.stego_key.textChanged.connect(self.refresh)
        self.encrypt = QCheckBox("Encrypt message (AES-GCM) for confidentiality")
        self.encrypt.toggled.connect(self._update_capacity)
        self.priv_pick = FilePicker("Private key", "PEM (*.pem)", str(keys_dir / "private_key.pem"))
        self.priv_pick.edit.textChanged.connect(self.refresh)

        self.go = QPushButton("Protect && save stego file…")
        self.go.clicked.connect(self.run_protect)
        self.hint = QLabel("")
        self.hint.setStyleSheet("color: gray;")
        go_row = QHBoxLayout()
        go_row.addWidget(self.go)
        go_row.addWidget(self.hint, 1)

        form = QFormLayout()
        form.addRow("Cover file", self.cover_pick)
        form.addRow("Preset", msg_row)
        form.addRow("Message", self.msg)
        form.addRow("LSBs used", self.k)
        form.addRow("", self.capacity)
        form.addRow("Stego key", self.stego_key)
        form.addRow("", self.encrypt)
        form.addRow("Private key", self.priv_pick)
        form.addRow("", go_row)

        self.cover_view = MediaView("Cover (before)")
        self.stego_view = MediaView("Stego (after)")
        self.diff_view = DiffView()
        views = QHBoxLayout()
        views.addWidget(self.cover_view)
        views.addWidget(self.stego_view)
        views.addWidget(self.diff_view)

        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumHeight(120)

        lay = QVBoxLayout(self)
        lay.addLayout(form)
        lay.addLayout(views, 1)
        lay.addWidget(self.log)
        self.refresh()

    def refresh(self):
        """Enable Protect only once the inputs are there. Capacity isn't checked
        here on purpose: the capacity-fail demo needs the button to be clickable."""
        missing = []
        if self.cover is None:
            missing.append("a cover file")
        if not self.stego_key.text():
            missing.append("a stego key")
        if not self.priv_pick.is_file():
            missing.append("a private key (Keys tab)")
        self.go.setEnabled(not missing)
        self.hint.setText("Needs " + ", ".join(missing) if missing else "")

    def _apply_preset(self, name):
        if name in messages.PRESETS:
            self.msg.setPlainText(messages.PRESETS[name])
            self.encrypt.setChecked(name == "Custom")

    def _load_text_file(self):
        path, _ = QFileDialog.getOpenFileName(self, "Message file", last_dir(), "Text (*.txt)")
        if not path:
            return
        remember_dir(path)
        try:
            self.msg.setPlainText(Path(path).read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError) as e:
            QMessageBox.warning(self, "Can't read text file",
                                f"{Path(path).name} couldn't be read as UTF-8 text:\n{e}")

    def load_cover(self):
        path = self.cover_pick.text()
        self.cover = None
        self.stego_view.clear()
        self.diff_view.clear()
        if not self.cover_pick.is_file():
            self.cover_view.clear()
        else:
            try:
                self.cover = media.load_cover(path)
                self.cover_view.show_file(path, self.cover)
            except Exception as e:
                self.cover_view.clear()
                self.capacity.setStyleSheet(f"color: {BAD_COLOUR};")
                self.capacity.setText(f"Can't load {Path(path).name}: {e}")
                self.refresh()
                return
        self._update_capacity()
        self.refresh()

    def _update_capacity(self):
        if self.cover is None:
            self.capacity.setText("")
            return
        k = self.k.value()
        cap = protect.capacity_bytes(self.cover, k)
        need = protect.body_size(self.cover, Path(self.cover_pick.text()).name,
                                 self.msg.toPlainText(), k, self.encrypt.isChecked())
        msg_len = len(self.msg.toPlainText().encode("utf-8"))
        fits = need <= cap
        self.capacity.setStyleSheet(f"color: {OK_COLOUR if fits else BAD_COLOUR};")
        self.capacity.setText(
            f"Payload {need:,} bytes (message {msg_len:,} + {need - msg_len:,} fields and signature) "
            f"of {cap:,} bytes available at {k} LSB(s), "
            + (f"{100 * need / cap:.1f}% used." if fits else "DOES NOT FIT."))

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
            with busy():
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

        # stego images are always saved losslessly, whatever the cover was
        if self.cover.kind == "audio":
            suffix, ext = ".wav", "WAV audio (*.wav)"
        else:
            suffix = cover_path.suffix.lower() if cover_path.suffix.lower() in media.IMAGE_EXTS else ".png"
            ext = "PNG image (*.png);;BMP image (*.bmp)"
        suggested = cover_path.with_name(f"{cover_path.stem}_stego{suffix}")
        out, _ = QFileDialog.getSaveFileName(self, "Save stego file", str(suggested), ext)
        if not out:
            return
        if not Path(out).suffix:
            out += suffix
        if Path(out).resolve() == cover_path.resolve():
            QMessageBox.warning(self, "Pick another name",
                                "That would overwrite the cover. Save the stego file under a new name.")
            return
        try:
            media.save_cover(stego, out)
        except Exception as e:
            QMessageBox.critical(self, "Save failed", str(e))
            return
        remember_dir(out)

        self.stego_view.show_file(out)
        self.diff_view.set_pair(self.cover, stego, info["k"])
        self.log.setPlainText(
            f"Saved {out}\n"
            f"Start offset {info['start']:,} of {info['carrier_units']:,} carrier bytes, "
            f"{info['k']} LSB(s), {info['body_len']:,} byte body, "
            f"{info['percent_used']:.2f}% of carrier used\n\n"
            + json.dumps(payload, indent=2))
        self.saved.emit(out)
