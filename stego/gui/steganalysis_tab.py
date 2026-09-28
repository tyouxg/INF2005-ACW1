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
        self.summary = QLabel("Plays the analyst: no stego key, no public key, just the file.")
        self.summary.setWordWrap(True)
        self.figure = Figure(figsize=(8, 2.4))
        self.canvas = FigureCanvasQTAgg(self.figure)
        self.text = QPlainTextEdit()
        self.text.setReadOnly(True)
        self.text.setPlaceholderText("Anything readable pulled out of the low bits shows up here")

        lay = QVBoxLayout(self)
        lay.addLayout(form)
        lay.addWidget(self.verdict)
        lay.addWidget(self.summary)
        lay.addWidget(QLabel("Where readable JSON shows up along the file (best k and bit alignment)"))
        lay.addWidget(self.canvas, 2)
        lay.addWidget(QLabel("What an analyst can read, without the key"))
        lay.addWidget(self.text, 1)

    def run(self):
        try:
            cover = media.load_cover(self.file_pick.text())
            with busy():
                r = steganalysis.scan(cover)
        except Exception as e:
            QMessageBox.warning(self, "Can't scan", str(e))
            return

        chi = (f"Chi-square attack (Westfeld & Pfitzmann): {100 * r.chi_square_embedded:.0f}% of 1 KB "
               "chunks look embedded. Real photos and audio already have noisy low bits, so this "
               "textbook test can't tell a clean cover from a stego file here.")
        if r.found:
            self.verdict.setText("HIDDEN TEXT FOUND")
            self.verdict.setStyleSheet(f"font-size: 20px; font-weight: bold; color: {FOUND_COLOUR};")
            self.summary.setText(
                f"Readable JSON sits in the lowest {r.k} bit(s) of carrier bytes {r.start:,} to "
                f"{r.end:,} (out of {r.carrier_units:,}). Its payload body isn't masked (a version 1 "
                f"file), so anyone can find and read it without the stego key. Version 2 masks the "
                f"body and doesn't show up.\n{chi}")
            self.text.setPlainText(r.text)
        else:
            self.verdict.setText("NOTHING FOUND")
            self.verdict.setStyleSheet(f"font-size: 20px; font-weight: bold; color: {CLEAN_COLOUR};")
            self.summary.setText("No readable structure in the low bits at any k from 1 to 8. Either the "
                                 f"file is clean, or its payload is masked (version 2).\n{chi}")
            self.text.clear()
        self._plot(r)

    def _plot(self, r):
        self.figure.clear()
        ax = self.figure.add_subplot(111)
        n = len(r.profile)
        # squeeze hundreds of thousands of positions into ~1500 bars, keeping each bar's peak
        bins = max(1, min(1500, n))
        edges = np.linspace(0, n, bins + 1).astype(int)[:-1]
        ax.plot(edges, np.maximum.reduceat(r.profile, edges), lw=0.8, color="#1565c0")
        ax.axhline(steganalysis.THRESHOLD, ls="--", lw=0.8, color="gray")
        if r.found:
            ax.axvspan(r.start, r.end, color=FOUND_COLOUR, alpha=0.2)
        ax.set_ylim(0, 1.05)
        ax.set_xlim(0, n)
        ax.set_xlabel("Carrier byte")
        ax.set_ylabel("Text score")
        self.figure.tight_layout()
        self.canvas.draw()
