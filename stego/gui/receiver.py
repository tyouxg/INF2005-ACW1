"""Receiver (party B): load a stego file, extract the payload and give a verdict."""

import json
from pathlib import Path

from PySide6.QtWidgets import (QCheckBox, QFormLayout, QHBoxLayout, QLabel, QLineEdit,
                               QMessageBox, QPlainTextEdit, QPushButton, QSpinBox,
                               QVBoxLayout, QWidget)

from ..core import crypto, media, protect
from .widgets import FilePicker, MediaView

COLOURS = {
    protect.AUTHENTIC: "#1b7f3b",
    protect.TAMPERED: "#b3261e",
    protect.SIGNATURE_INVALID: "#b3261e",
    protect.PAYLOAD_MISSING: "#a15c00",
    protect.WRONG_START: "#a15c00",
    protect.CANNOT_VERIFY: "#555555",
}


class ReceiverTab(QWidget):
    def __init__(self, keys_dir: Path):
        super().__init__()
        self.file_pick = FilePicker("Choose stego file",
                                    "Stego files (*.png *.bmp *.wav)")
        self.file_pick.edit.textChanged.connect(self._preview)
        self.stego_key = QLineEdit()
        self.stego_key.setEchoMode(QLineEdit.Password)
        self.pub_pick = FilePicker("Public key", "PEM (*.pem)", str(keys_dir / "public_key.pem"))

        # For the wrong-start-location demo: force a specific offset instead of deriving it
        self.force_start = QCheckBox("Force start offset")
        self.start = QSpinBox()
        self.start.setRange(0, 2_000_000_000)
        self.start.setEnabled(False)
        self.force_start.toggled.connect(self.start.setEnabled)
        start_row = QHBoxLayout()
        start_row.addWidget(self.force_start)
        start_row.addWidget(self.start, 1)

        go = QPushButton("Extract && verify")
        go.clicked.connect(self.run_verify)

        form = QFormLayout()
        form.addRow("Stego file", self.file_pick)
        form.addRow("Stego key", self.stego_key)
        form.addRow("Public key", self.pub_pick)
        form.addRow("Testing", start_row)
        form.addRow("", go)

        self.view = MediaView("Received file")
        self.verdict = QLabel("")
        self.verdict.setStyleSheet("font-size: 22px; font-weight: bold;")
        self.reason = QLabel("")
        self.reason.setWordWrap(True)
        self.message = QPlainTextEdit()
        self.message.setReadOnly(True)
        self.message.setPlaceholderText("Extracted message appears here")
        self.details = QPlainTextEdit()
        self.details.setReadOnly(True)

        right = QVBoxLayout()
        right.addWidget(self.verdict)
        right.addWidget(self.reason)
        right.addWidget(QLabel("Hidden message"))
        right.addWidget(self.message, 1)
        right.addWidget(QLabel("Payload and details"))
        right.addWidget(self.details, 2)

        body = QHBoxLayout()
        body.addWidget(self.view, 1)
        body.addLayout(right, 1)

        lay = QVBoxLayout(self)
        lay.addLayout(form)
        lay.addLayout(body, 1)

    def _preview(self, path):
        if Path(path).is_file():
            try:
                self.view.show_file(path)
                return
            except Exception:
                pass
        self.view.clear()

    def run_verify(self):
        try:
            cover = media.load_cover(self.file_pick.text())
            pub = crypto.load_public_key(self.pub_pick.text())
        except Exception as e:
            QMessageBox.warning(self, "Can't load", str(e))
            return

        start = self.start.value() if self.force_start.isChecked() else None
        res = protect.verify(cover, self.stego_key.text(), pub, start)

        self.verdict.setText(res.verdict.upper())
        self.verdict.setStyleSheet(f"font-size: 22px; font-weight: bold; "
                                   f"color: {COLOURS[res.verdict]};")
        self.reason.setText(res.reason)
        if res.message is not None:
            self.message.setPlainText(res.message)
        elif res.payload and res.payload["message"].get("enc"):
            self.message.setPlainText("(encrypted, could not decrypt)")
        else:
            self.message.clear()
        self.details.setPlainText(json.dumps({"details": res.details, "payload": res.payload},
                                             indent=2))
