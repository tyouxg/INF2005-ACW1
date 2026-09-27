"""Attack Lab tab: run every simulated attack on a stego file, show the verdicts."""

from pathlib import Path

from PySide6.QtGui import QColor
from PySide6.QtWidgets import (QFormLayout, QLabel, QLineEdit, QMessageBox, QPushButton,
                               QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget)

from ..core import attacks, crypto, media
from .widgets import FilePicker, busy

OK_COLOUR, BAD_COLOUR = "#1b7f3b", "#b3261e"


class AttackLabTab(QWidget):
    def __init__(self, keys_dir: Path):
        super().__init__()
        self.file_pick = FilePicker("Choose stego file", "Stego files (*.png *.bmp *.wav)")
        self.stego_key = QLineEdit()
        self.stego_key.setEchoMode(QLineEdit.Password)
        self.stego_key.setPlaceholderText("Same stego key the sender used")
        self.pub_pick = FilePicker("Public key", "PEM (*.pem)", str(keys_dir / "public_key.pem"))
        run = QPushButton("Run all attacks")
        run.clicked.connect(self.run)

        form = QFormLayout()
        form.addRow("Stego file", self.file_pick)
        form.addRow("Stego key", self.stego_key)
        form.addRow("Public key", self.pub_pick)
        form.addRow("", run)

        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["Attack", "What the attacker did", "Expected", "Got"])
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.summary = QLabel("Hover over a verdict to see why verify() gave it.")

        lay = QVBoxLayout(self)
        lay.addLayout(form)
        lay.addWidget(self.table, 1)
        lay.addWidget(self.summary)

    def run(self):
        # All the attack logic lives in core/attacks.py, this just shows the rows
        try:
            stego = media.load_cover(self.file_pick.text())
            pub = crypto.load_public_key(self.pub_pick.text())
            with busy():
                results = attacks.run_all(stego, self.stego_key.text(), pub)
        except Exception as e:
            QMessageBox.warning(self, "Can't run the attacks", str(e))
            return

        self.table.setRowCount(len(results))
        for row, r in enumerate(results):
            cells = [r.name, r.what, " / ".join(r.expected), r.got]
            for col, text in enumerate(cells):
                self.table.setItem(row, col, QTableWidgetItem(text))
            got = self.table.item(row, 3)
            got.setForeground(QColor(OK_COLOUR if r.passed else BAD_COLOUR))
            got.setToolTip(r.reason)
        self.table.resizeColumnsToContents()

        caught = sum(r.passed for r in results)
        self.summary.setText(f"{caught} of {len(results)} attacks detected with the expected verdict.")
