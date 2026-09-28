"""Steganalysis tab: check any file for hidden data WITHOUT the stego key."""

import numpy as np
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure
from PySide6.QtWidgets import (QFormLayout, QLabel, QMessageBox, QPlainTextEdit, QPushButton,
                               QVBoxLayout, QWidget)

from ..core import media, steganalysis
from .widgets import FilePicker, busy

FOUND_COLOUR, CLEAN_COLOUR = "#b3261e", "#1b7f3b"


class SteganalysisTab(QWidget):
    def __init__(self):
        super().__init__()
        self.file_pick = FilePicker("Choose any image, WAV or video",
                                    "Media (*.png *.bmp *.jpg *.jpeg *.wav *.mkv *.avi *.mp4 *.mov)")
        run = QPushButton("Scan for hidden data (no key needed)")
        run.clicked.connect(self.run)
        form = QFormLayout()
        form.addRow("File", self.file_pick)
        form.addRow("", run)

        self.verdict = QLabel("")
        self.verdict.setStyleSheet("font-size: 20px; font-weight: bold;")
        self.summary = QLabel("Plays the analyst: statistical blind detection using chi-square tests.")
        self.summary.setWordWrap(True)
        self.figure = Figure(figsize=(8, 2.4))
        self.canvas = FigureCanvasQTAgg(self.figure)
        self.text = QPlainTextEdit()
        self.text.setReadOnly(True)
        self.text.setPlaceholderText("Statistical scan diagnostics will display here")

        lay = QVBoxLayout(self)
        lay.addLayout(form)
        lay.addWidget(self.verdict)
        lay.addWidget(self.summary)
        lay.addWidget(QLabel("Chi-square embedding probability profile across carrier bytes"))
        lay.addWidget(self.canvas, 2)
        lay.addWidget(QLabel("Statistical scan diagnostics"))
        lay.addWidget(self.text, 1)

    def run(self):
        try:
            cover = media.load_cover(self.file_pick.text())
            with busy():
                r = steganalysis.scan(cover)
        except Exception as e:
            QMessageBox.warning(self, "Can't scan", str(e))
            return

        if r.found:
            self.verdict.setText("LIKELY EMBEDDED")
            self.verdict.setStyleSheet(f"font-size: 20px; font-weight: bold; color: {FOUND_COLOUR};")
            self.summary.setText(
                f"Statistical anomaly detected across {100 * r.chi_square_embedded:.1f}% of evaluated chunks. "
                f"Suspicious distributions span carrier bytes {r.start:,} to {r.end:,} (out of {r.carrier_units:,})."
            )
        else:
            self.verdict.setText("LIKELY CLEAN")
            self.verdict.setStyleSheet(f"font-size: 20px; font-weight: bold; color: {CLEAN_COLOUR};")
            self.summary.setText(
                f"Only {100 * r.chi_square_embedded:.1f}% of chunks scored above threshold. "
                f"No persistent statistical signs of LSB replacement were identified."
            )
        self.text.setPlainText(r.text)
        self._plot(r)

    def _plot(self, r):
        self.figure.clear()
        ax = self.figure.add_subplot(111)
        n = len(r.profile)
        bins = max(1, min(1500, n))
        edges = np.linspace(0, n, bins + 1).astype(int)[:-1]
        ax.plot(edges, np.maximum.reduceat(r.profile, edges), lw=0.8, color="#1565c0")
        ax.axhline(steganalysis.THRESHOLD, ls="--", lw=0.8, color="gray")
        if r.found and r.start is not None and r.end is not None:
            ax.axvspan(r.start, r.end, color=FOUND_COLOUR, alpha=0.2)
        ax.set_ylim(0, 1.05)
        ax.set_xlim(0, n)
        ax.set_xlabel("Carrier byte")
        ax.set_ylabel("Chi-square p-value")
        self.figure.tight_layout()
        self.canvas.draw()