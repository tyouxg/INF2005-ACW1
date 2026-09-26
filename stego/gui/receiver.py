"""Receiver (party B): load a stego file, extract the payload and give a verdict."""

import json
from pathlib import Path

from PySide6.QtWidgets import (QCheckBox, QFormLayout, QHBoxLayout, QLabel, QLineEdit,
                               QMessageBox, QPlainTextEdit, QPushButton, QSpinBox,
                               QVBoxLayout, QWidget)

from ..core import crypto, media, protect
from .widgets import FilePicker, MediaView, busy

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
        self.stego_key.setPlaceholderText("Same stego key the sender used")
        self.stego_key.textChanged.connect(self.refresh)
        self.pub_pick = FilePicker("Public key", "PEM (*.pem)", str(keys_dir / "public_key.pem"))
        self.pub_pick.edit.textChanged.connect(self.refresh)

        # For the wrong-start-location demo: force a specific offset instead of deriving it
        self.force_start = QCheckBox("Force start offset")
        self.start = QSpinBox()
        self.start.setRange(0, 2_000_000_000)
        self.start.setEnabled(False)
        self.force_start.toggled.connect(self.start.setEnabled)
        start_row = QHBoxLayout()
        start_row.addWidget(self.force_start)
        start_row.addWidget(self.start, 1)

        self.go = QPushButton("Extract && verify")
        self.go.clicked.connect(self.run_verify)
        self.hint = QLabel("")
        self.hint.setStyleSheet("color: gray;")
        go_row = QHBoxLayout()
        go_row.addWidget(self.go)
        go_row.addWidget(self.hint, 1)

        form = QFormLayout()
        form.addRow("Stego file", self.file_pick)
        form.addRow("Stego key", self.stego_key)
        form.addRow("Public key", self.pub_pick)
        form.addRow("Testing", start_row)
        form.addRow("", go_row)

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
        self.refresh()

    def refresh(self):
        missing = []
        if not self.file_pick.is_file():
            missing.append("a stego file")
        if not self.stego_key.text():
            missing.append("the stego key")
        if not self.pub_pick.is_file():
            missing.append("the sender's public key")
        self.go.setEnabled(not missing)
        self.hint.setText("Needs " + ", ".join(missing) if missing else "")

    def _clear_result(self):
        self.verdict.clear()
        self.reason.clear()
        self.message.clear()
        self.details.clear()

    def _preview(self):
        # old verdict no longer applies to a different file
        self._clear_result()
        self.refresh()
        if self.file_pick.is_file():
            try:
                self.view.show_file(self.file_pick.text())
                return
            except Exception as e:
                self.view.clear()
                self.reason.setText(f"Can't open {Path(self.file_pick.text()).name}: {e}")
                return
        self.view.clear()

    def run_verify(self):
        try:
            cover = media.load_cover(self.file_pick.text())
        except Exception as e:
            QMessageBox.warning(self, "Can't load stego file", str(e))
            return
        try:
            pub = crypto.load_public_key(self.pub_pick.text())
        except Exception as e:
            QMessageBox.warning(self, "Can't load public key",
                                f"{e}\n\nUse the sender's public_key.pem, not a private key.")
            return

        start = self.start.value() if self.force_start.isChecked() else None
        with busy():
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
