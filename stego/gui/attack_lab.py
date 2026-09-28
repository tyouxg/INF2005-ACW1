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
        self.file_pick = FilePicker("Choose stego file", "Stego files (*.png *.bmp *.wav *.mkv *.avi)")
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

        self.table = QTableWidget(0, 6)
        # "Check it targets" follows verify()'s order, so reading down the table
        # walks through the defences one by one. "Payload recovered" is where
        # robust mode shows off: the verdict still flags the change, but the
        # signed message came out intact.
        self.table.setHorizontalHeaderLabels(["Attack", "Check it targets", "What the attacker did",
                                              "Expected", "Got", "Payload recovered"])
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.summary = QLabel("Hover over an attack to see what the attacker has, or over a "
                              "verdict to see why verify() gave it.")

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
            cells = [f"{r.number}. {r.name}", r.check, r.what, " / ".join(r.expected), r.got,
                     "yes" if r.recovered else "no"]
            for col, text in enumerate(cells):
                self.table.setItem(row, col, QTableWidgetItem(text))
            self.table.item(row, 0).setToolTip(f"Attacker has: {r.attacker_has}")
            got = self.table.item(row, 4)
            got.setForeground(QColor(OK_COLOUR if r.passed else BAD_COLOUR))
            got.setToolTip(r.reason)
        self.table.verticalHeader().setVisible(False)   # the attack number is in column 0
        self.table.resizeColumnsToContents()

        caught = sum(r.passed for r in results)
        self.summary.setText(f"{caught} of {len(results)} attacks detected with the expected verdict. "
                             f"The signed payload survived {sum(r.recovered for r in results)} of them.")
