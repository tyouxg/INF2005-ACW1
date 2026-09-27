import sys
from pathlib import Path

from PySide6.QtWidgets import (QApplication, QLabel, QMainWindow, QMessageBox, QPushButton,
                               QTabWidget, QVBoxLayout, QWidget)

from ..core import crypto
from .receiver import ReceiverTab
from .sender import SenderTab

KEYS_DIR = Path(__file__).resolve().parents[2] / "keys"


class KeysTab(QWidget):
    def __init__(self):
        super().__init__()
        self.status = QLabel()
        self.status.setWordWrap(True)
        gen = QPushButton("Generate new Ed25519 key pair")
        gen.clicked.connect(self.generate)
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel(f"Keys folder: {KEYS_DIR}"))
        lay.addWidget(gen)
        lay.addWidget(self.status)
        lay.addStretch(1)
        self.refresh()

    def refresh(self):
        pub = KEYS_DIR / "public_key.pem"
        if pub.exists():
            fp = crypto.public_key_fingerprint(crypto.load_public_key(pub))
            self.status.setText(f"Public key fingerprint: {fp}\n"
                                "Share public_key.pem with the receiver. Keep private_key.pem to yourself.")
        else:
            self.status.setText("No key pair yet.")

    def generate(self):
        if (KEYS_DIR / "private_key.pem").exists():
            ok = QMessageBox.question(self, "Overwrite?",
                                      "A key pair already exists. Files signed with the old key "
                                      "won't verify against the new public key. Replace it?")
            if ok != QMessageBox.Yes:
                return
        crypto.save_keypair(crypto.generate_keypair(), KEYS_DIR)
        self.refresh()


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("INF2005 Stego Verifier")
        self.resize(1100, 850)
        self.sender = SenderTab(KEYS_DIR)
        self.receiver = ReceiverTab(KEYS_DIR)
        # saves re-picking the file when A and B are demoed on the same laptop
        self.sender.saved.connect(self.receiver.file_pick.edit.setText)
        tabs = QTabWidget()
        tabs.addTab(self.sender, "Sender (A)")
        tabs.addTab(self.receiver, "Receiver (B)")
        tabs.addTab(KeysTab(), "Keys")
        # a key pair made in the Keys tab should enable the buttons straight away
        tabs.currentChanged.connect(self.sender.refresh)
        tabs.currentChanged.connect(self.receiver.refresh)
        self.setCentralWidget(tabs)


def main():
    app = QApplication(sys.argv)
    win = MainWindow()
    win.show()
    sys.exit(app.exec())
