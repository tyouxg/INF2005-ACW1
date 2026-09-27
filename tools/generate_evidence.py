r"""Regenerate the ACW1 test evidence: CLI logs, GUI screenshots and a results summary.

Run from the repository root:
    .venv\Scripts\python tools\generate_evidence.py

Everything lands in tests/evidence/ (files/, logs/, screenshots/, results.json).
It also covers the optional challenges: video covers, robust mode and steganalysis.
It drives the real CLI and the real GUI (offscreen), uses the team's committed
demo key pair so anyone can re-check the files, and runs inside a throwaway
replay store so the real keys/seen_nonces.json is never touched.
"""

import contextlib
import hashlib
import io
import json
import os
import platform
import shutil
import subprocess
import sys
import wave
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
os.chdir(ROOT)                      # so every path in the logs is short and relative
sys.path.insert(0, str(ROOT))

# The GUI renders offscreen. Qt's offscreen mode ships no fonts, so on Windows
# point it at the system fonts, otherwise every label comes out as boxes.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
if Path("C:/Windows/Fonts").is_dir():
    os.environ.setdefault("QT_QPA_FONTDIR", "C:/Windows/Fonts")

import matplotlib.cbook                                              # noqa: E402
import numpy as np                                                   # noqa: E402
from PIL import Image                                                # noqa: E402
from PySide6.QtGui import QFont                                      # noqa: E402
from PySide6.QtWidgets import QApplication                           # noqa: E402

from stego import cli, messages                                      # noqa: E402
from stego.core import attacks, crypto, media, protect, replay, steganalysis, visual  # noqa: E402
from stego.gui import receiver as receiver_mod                       # noqa: E402
from stego.gui import sender as sender_mod                           # noqa: E402
from stego.gui.app import MainWindow                                 # noqa: E402

OUT = Path("tests/evidence")
FILES, LOGS, SHOTS = OUT / "files", OUT / "logs", OUT / "screenshots"
KEY = "p6-4-demo-key"               # coursework demo stego key, not a real secret
PRIV, PUB = "keys/private_key.pem", "keys/public_key.pem"

cases = []                          # one entry per demo case, written to results.json


# --- small helpers ---

def cli_run(args: list[str]) -> str:
    """Run the real CLI in-process and return a transcript: the command, then its output."""
    buf = io.StringIO()
    code = 0
    with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
        try:
            cli.main(args)
        except SystemExit as e:
            # verify exits 1 for anything but Authentic; protect exits with the
            # capacity message as a string
            if isinstance(e.code, str):
                buf.write(e.code + "\n")
                code = 1
            else:
                code = e.code or 0
    shown = " ".join(f'"{a}"' if " " in a else a for a in args)
    return f"$ python -m stego.cli {shown}\n{buf.getvalue()}(exit code {code})\n"


def write_log(name: str, *parts: str) -> str:
    path = LOGS / f"{name}.txt"
    path.write_text("\n".join(parts), encoding="utf-8")
    return path.as_posix()


def sha256(path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def add_case(cid, title, cover, kind, requirement, expected, actual, log, shots, notes=""):
    cases.append({
        "id": cid, "title": title, "cover": cover, "kind": kind,
        "requirement": requirement, "expected": expected, "actual": actual,
        "passed": actual == expected, "log": log, "screenshots": shots, "notes": notes,
    })
    print(f"  {cid:4} {title:55} expected {expected:22} got {actual:22} "
          f"{'OK' if actual == expected else 'MISMATCH'}")


def verdict_of(path, key=KEY, pub=PUB) -> tuple[str, dict]:
    res = protect.verify(media.load_cover(path), key, crypto.load_public_key(pub))
    return res.verdict, res.details


def payload_units(details) -> np.ndarray:
    return attacks.payload_region(details)


# --- inputs ---

def make_inputs():
    # A real photo makes the before/after comparison meaningful. This one is
    # Grace Hopper's portrait (US Navy, public domain), shipped with matplotlib.
    src = matplotlib.cbook.get_sample_data("grace_hopper.jpg", asfileobj=False)
    img = Image.open(src).convert("RGB")
    img = img.resize((400, round(400 * img.height / img.width)))
    img.save(FILES / "image_cover.png")
    # A tiny crop for the capacity check: far too small for the long message at 1 LSB
    img.crop((180, 120, 204, 144)).save(FILES / "image_tiny.png")

    # First 4 s of M2's generated stereo track (tools/generate_audio_samples.py)
    with wave.open("samples/audio/cover_stereo_music.wav", "rb") as w:
        params = w.getparams()
        frames = w.readframes(params.framerate * 4)
    with wave.open(str(FILES / "audio_cover.wav"), "wb") as w:
        w.setnchannels(params.nchannels)
        w.setsampwidth(params.sampwidth)
        w.setframerate(params.framerate)
        w.writeframes(frames)


# --- GUI driving ---

class Gui:
    """Drives the real MainWindow. Only the file dialogs and pop-ups are stubbed,
    everything else is the same code path a user clicking through would hit."""

    def __init__(self):
        self.app = QApplication.instance() or QApplication([])
        if platform.system() == "Windows":
            self.app.setFont(QFont("Segoe UI", 9))
        self.win = MainWindow()
        self.win.resize(1150, 860)
        self.tabs = self.win.centralWidget()
        self.popups = []
        # no one is there to click OK, so record pop-ups instead of blocking
        for mod in (sender_mod, receiver_mod):
            mod.QMessageBox.critical = lambda _p, title, text: self.popups.append(f"{title}: {text}")
            mod.QMessageBox.warning = lambda _p, title, text: self.popups.append(f"{title}: {text}")
        s = self.win.sender
        s.priv_pick.edit.setText(PRIV)
        self.win.receiver.pub_pick.edit.setText(PUB)
        self.win.attack_lab.pub_pick.edit.setText(PUB)
        self.win.show()

    def pump(self):
        self.app.processEvents()

    def shot(self, name: str, tab: int) -> str:
        self.tabs.setCurrentIndex(tab)
        self.pump()
        path = SHOTS / f"{name}.png"
        self.win.grab().save(str(path))
        return path.as_posix()

    def protect(self, cover, preset, k, out, key=KEY, robust="Off") -> str:
        s = self.win.sender
        s.cover_pick.edit.setText(str(cover))
        s.preset.setCurrentText(preset)
        s.k.setValue(k)
        s.robust.setCurrentText(robust)
        s.stego_key.setText(key)
        # answer the "Save stego file" dialog with our chosen path
        sender_mod.QFileDialog.getSaveFileName = lambda *a, **kw: (str(out), "")
        s.run_protect()
        self.pump()
        return s.log.toPlainText()

    def verify(self, path, key=KEY, pub=PUB):
        r = self.win.receiver
        r.pub_pick.edit.setText(pub)
        r.file_pick.edit.setText(str(path))
        r.stego_key.setText(key)
        r.run_verify()
        self.pump()
        return r.verdict.text().title()

    def scan(self, path):
        t = self.win.steganalysis
        t.file_pick.edit.setText(str(path))
        t.run()
        self.pump()
        return t.verdict.text()

    def attack_lab(self, path, key=KEY, pub=PUB):
        a = self.win.attack_lab
        a.file_pick.edit.setText(str(path))
        a.stego_key.setText(key)
        a.pub_pick.edit.setText(pub)
        a.run()
        self.pump()


# --- the demo cases ---

def positive(gui, cid, title, cover, kind, preset, k, name, requirement, robust="Off"):
    out = FILES / name
    sender_log = gui.protect(cover, preset, k, out, robust=robust)
    s1 = gui.shot(f"{cid}_sender", 0)
    replay.clear()
    verify_log = cli_run(["verify", out.as_posix(), "--key", KEY, "--pub", PUB])
    replay.clear()          # the GUI check below is its own independent verification
    got = gui.verify(out)
    s2 = gui.shot(f"{cid}_receiver", 1)
    log = write_log(cid, f"# {title}", "## Sender tab log (GUI)", sender_log,
                    "## Receiver side (CLI)", verify_log)
    add_case(cid, title, cover.as_posix(), kind, requirement, protect.AUTHENTIC,
             protect.AUTHENTIC if "Verdict: Authentic" in verify_log and got == "Authentic"
             else got, log, [s1, s2])
    return out


def black_out_rows(stego_path, out):
    # "Redact" a 90 x 40 block of the photo, away from the rows the payload sits in,
    # so the signature stays valid and only the media hash can catch it
    cover = media.load_cover(stego_path)
    _, details = verdict_of(stego_path)
    w, h = cover.params["width"], cover.params["height"]
    busy_rows = set((payload_units(details) // 3 // w).tolist())
    top = next(r for r in range(20, h - 40) if not busy_rows & set(range(r, r + 40)))
    rgb = visual.image_rgb(cover).copy()
    rgb[top:top + 40, 150:240] = 0
    Image.fromarray(rgb).save(out)
    return top


def amplify_clear_section(stego_path, out):
    # Make half a second 35% louder somewhere the payload isn't, like a quick
    # edit in Audacity. Same length, so the start location still lines up.
    cover = media.load_cover(stego_path)
    _, details = verdict_of(stego_path)
    p = cover.params
    busy_frames = set((payload_units(details) // p["channels"]).tolist())
    span = p["framerate"] // 2
    start = next(f for f in range(0, p["nframes"] - span, span)
                 if not busy_frames & set(range(f, f + span)))
    samples = cover.data.view("<i2").reshape(p["nframes"], p["channels"]).copy()
    louder = np.clip(samples[start:start + span].astype(float) * 1.35, -32768, 32767)
    samples[start:start + span] = louder.astype("<i2")
    media.save_cover(media.Cover("audio", samples.reshape(-1).view(np.uint8).copy(),
                                 cover.step, dict(p)), out)
    return start / p["framerate"]


def negative_cases(gui, p1, p2):
    # N1 capacity check: long message into a 24x24 image
    tiny = FILES / "image_tiny.png"
    long_txt = FILES / "long_message.txt"
    long_txt.write_text(messages.LONG, encoding="utf-8")
    log1 = cli_run(["capacity", tiny.as_posix(), "-k", "1", "--msg-file", long_txt.as_posix()])
    log1 += "\n" + cli_run(["protect", tiny.as_posix(), (FILES / "n1_should_not_exist.png").as_posix(),
                           "-k", "1", "--key", KEY, "--msg-file", long_txt.as_posix(), "--priv", PRIV])
    log1 += "\n" + cli_run(["capacity", tiny.as_posix(), "-k", "8", "--msg-file", long_txt.as_posix()])
    gui.popups.clear()
    sender_log = gui.protect(tiny, "Long (project overview)", 1, FILES / "n1_should_not_exist.png")
    s = gui.shot("N1_sender_capacity_fail", 0)
    blocked = "DOES NOT FIT" in gui.win.sender.capacity.text() and not (FILES / "n1_should_not_exist.png").exists()
    log = write_log("N1", "# N1 Capacity check: long message into a 24x24 image at 1 LSB",
                    log1, "## GUI pop-up", *gui.popups, "## Sender tab log (GUI)", sender_log)
    add_case("N1", "Capacity check: payload larger than cover", tiny.as_posix(), "image",
             "Capacity check / LSB selection", "Blocked", "Blocked" if blocked else "Not blocked",
             log, [s], "At 1 LSB the long message doesn't fit, at 8 LSBs it does.")

    # N2 image edited after protection
    n2 = FILES / "n2_image_tampered.png"
    top = black_out_rows(p1, n2)
    log2 = cli_run(["verify", n2.as_posix(), "--key", KEY, "--pub", PUB])
    got = gui.verify(n2)
    s = gui.shot("N2_receiver_tampered", 1)
    add_case("N2", "Image edited after protection (block blacked out)", n2.as_posix(), "image",
             "Negative image case", protect.TAMPERED, got,
             write_log("N2", f"# N2 Rows {top}-{top + 39}, columns 150-239 set to black", log2), [s],
             "The payload rows were left alone, so the signature is valid and the media hash catches it.")

    # N3 audio edited after protection
    n3 = FILES / "n3_audio_tampered.wav"
    at = amplify_clear_section(p2, n3)
    log3 = cli_run(["verify", n3.as_posix(), "--key", KEY, "--pub", PUB])
    got = gui.verify(n3)
    s = gui.shot("N3_receiver_tampered", 1)
    add_case("N3", "Audio edited after protection (0.5 s made 35% louder)", n3.as_posix(), "audio",
             "Negative audio case", protect.TAMPERED, got,
             write_log("N3", f"# N3 Amplified 0.5 s starting at {at:.2f} s", log3), [s])

    # N4 someone else signs a payload: they know the stego key, not A's private key
    eve_dir = FILES / "attacker_keys"
    crypto.save_keypair(crypto.generate_keypair(), eve_dir)
    n4 = FILES / "n4_image_forged.png"
    log4 = cli_run(["protect", "tests/evidence/files/image_cover.png", n4.as_posix(), "-k", "2",
                    "--key", KEY, "--msg", "Release approved: batch 99", "--priv",
                    (eve_dir / "private_key.pem").as_posix()])
    log4 += "\n" + cli_run(["verify", n4.as_posix(), "--key", KEY, "--pub", PUB])
    got = gui.verify(n4)
    s = gui.shot("N4_receiver_signature_invalid", 1)
    add_case("N4", "Forged payload signed with an attacker's key", n4.as_posix(), "image",
             "Signature verification", protect.SIGNATURE_INVALID, got,
             write_log("N4", "# N4 Attacker signs with their own key, receiver uses A's public key", log4),
             [s], "Attacker key pair generated only for this test, in files/attacker_keys/.")

    # N5 wrong stego key
    log5 = cli_run(["verify", p2.as_posix(), "--key", "wrong-guess", "--pub", PUB])
    got = gui.verify(p2, key="wrong-guess")
    s = gui.shot("N5_receiver_wrong_key", 1)
    add_case("N5", "Wrong stego key (start location can't be found)", p2.as_posix(), "audio",
             "Start-location security", protect.WRONG_START, got, write_log("N5", "# N5", log5), [s])

    # N6 replay: same genuine file presented twice, then history cleared
    replay.clear()
    first = cli_run(["verify", p1.as_posix(), "--key", KEY, "--pub", PUB])
    second = cli_run(["verify", p1.as_posix(), "--key", KEY, "--pub", PUB])
    got = gui.verify(p1)
    s = gui.shot("N6_receiver_replay", 1)
    cleared = cli_run(["clear-replay"])
    third = cli_run(["verify", p1.as_posix(), "--key", KEY, "--pub", PUB])
    add_case("N6", "Replay: the same genuine file presented again", p1.as_posix(), "image",
             "Replay detection (team addition)", protect.REPLAY_DETECTED, got,
             write_log("N6", "# N6 First verify", first, "# Second verify of the same file", second,
                       "# Clearing the history (what we do before the demo)", cleared,
                       "# Verify again after clearing", third), [s])

    # N7 limitation: the stego image goes through JPEG
    n7 = FILES / "n7_after_jpeg.png"
    buf = io.BytesIO()
    Image.open(p1).save(buf, "JPEG", quality=95)
    Image.open(buf).convert("RGB").save(n7)   # decoded pixels, back in a format we accept
    log7 = cli_run(["verify", n7.as_posix(), "--key", KEY, "--pub", PUB])
    verdict7, _ = verdict_of(n7)
    add_case("N7", "Limitation: stego image re-saved as JPEG (quality 95)", n7.as_posix(), "image",
             "Limitations", "Not authentic", "Not authentic" if verdict7 != protect.AUTHENTIC else verdict7,
             write_log("N7", "# N7 JPEG round trip destroys the LSBs", log7), [],
             f"verify() said {verdict7}: the payload doesn't survive lossy compression.")


# --- optional challenges: video, robust mode, steganalysis ---

def make_video(path):
    # A short pan across the same photo, so the video has real content in it
    img = np.array(Image.open(FILES / "image_cover.png"))
    frames = np.stack([img[40 + 4 * i: 280 + 4 * i, 40:360] for i in range(24)])
    media.save_cover(media.Cover("video", frames.reshape(-1).copy(), 1,
                                 {"width": 320, "height": 240, "frames": 24, "fps": 12.0}), path)


def black_out_other_frame(stego_path, out, payload_frame):
    # Black out a box in a frame that doesn't hold the payload (the first one,
    # or the last if the key happened to put the payload in the first)
    t = media.load_cover(stego_path)
    p = t.params
    target = 0 if payload_frame != 0 else p["frames"] - 1
    size = p["width"] * p["height"] * 3
    frame = t.data[target * size:(target + 1) * size].reshape(p["height"], p["width"], 3)
    frame[60:140, 100:220] = 0
    media.save_cover(t, out)
    return target


def attack_rows(path, key=KEY):
    rows = attacks.run_all(media.load_cover(path), key, crypto.load_public_key(PUB))
    return [{"name": r.name, "what": r.what, "expected": list(r.expected), "got": r.got,
             "passed": r.passed, "recovered": r.recovered, "reason": r.reason} for r in rows]


def advanced_cases(gui, image_cover):
    adv = {}

    # Video: positive, then a different frame edited after protection, then the Attack Lab
    video_cover = FILES / "video_cover.mkv"
    make_video(video_cover)
    v1 = positive(gui, "V1", "Video (FFV1 .mkv), short message, 2 LSBs", video_cover, "video",
                  "Short (learning outcome)", 2, "v1_video_stego.mkv",
                  "Optional challenge: video cover object")
    frame = visual.first_changed_frame(media.load_cover(video_cover), media.load_cover(v1))
    v2 = FILES / "v2_video_tampered.mkv"
    edited = black_out_other_frame(v1, v2, frame)
    log = cli_run(["verify", v2.as_posix(), "--key", KEY, "--pub", PUB])
    got = gui.verify(v2)
    shot = gui.shot("V2_receiver_video_tampered", 1)
    add_case("V2", "Video: a different frame edited after protection", v2.as_posix(), "video",
             "Optional challenge: video cover object", protect.TAMPERED, got,
             write_log("V2", f"# V2 Box blacked out in frame {edited + 1}", log), [shot],
             f"The payload sits in frame {frame + 1} of 24 and frame {edited + 1} was edited. It is "
             "still caught, because the media hash covers every frame.")
    adv["video"] = {"payload_frame": frame + 1, "frames": 24, "attacks": attack_rows(v1)}
    gui.attack_lab(v1)
    gui.shot("attack_lab_video", 2)

    # Robust mode: the same cover, normal vs x5 repetition, same attacks
    robust_file = FILES / "r1_image_robust_x5.png"
    positive(gui, "R1", "Image, robust mode (x5 repetition), 2 LSBs", image_cover, "image",
             "Short (learning outcome)", 2, robust_file.name,
             "Optional challenge: robust embedding", robust="x5 repetition")
    adv["robust"] = {"normal": attack_rows(FILES / "p1_image_stego.png"),
                     "robust": attack_rows(robust_file)}
    gui.attack_lab(robust_file)
    gui.shot("attack_lab_robust", 2)
    normal_ok = {r["name"] for r in adv["robust"]["normal"] if r["recovered"]}
    survived = sorted({r["name"] for r in adv["robust"]["robust"] if r["recovered"]} - normal_ok)
    ok = {"Mild LSB noise", "Scratch over payload"} <= set(survived)
    add_case("R2", "Robust file vs normal file under noise and a scratch", robust_file.as_posix(),
             "image", "Optional challenge: robust embedding", "Payload recovered",
             "Payload recovered" if ok else "Lost",
             write_log("R2", json.dumps(adv["robust"], indent=2)), [],
             "Only the robust file keeps its signed payload after: " + ", ".join(survived) + ".")

    # Steganalysis: an old version 1 file, M2's real sample, our v2 files, a clean cover
    legacy = FILES / "s1_legacy_v1_stego.png"
    st, _, _ = protect.protect(media.load_cover(image_cover), image_cover.name, messages.SHORT, 2,
                               KEY, crypto.load_private_key(PRIV), version=1)
    media.save_cover(st, legacy)
    scans = []
    for label, path in (("Version 1 file (body not masked)", legacy),
                        ("M2's audio sample (made with version 1)",
                         Path("samples/audio/stego_long_message.wav")),
                        ("P1, made with version 2 (body masked)", FILES / "p1_image_stego.png"),
                        ("R1, robust version 2 file", robust_file),
                        ("Clean cover, nothing hidden", image_cover)):
        r = steganalysis.scan(media.load_cover(path))
        scans.append({"label": label, "file": path.as_posix(), "found": r.found, "k": r.k,
                      "start": r.start, "end": r.end, "text": r.text[:400],
                      "chi_square_embedded": round(r.chi_square_embedded, 3)})
    adv["steganalysis"] = scans
    scan_log = "\n".join(cli_run(["scan", x["file"]]) for x in scans)
    log = write_log("S1", "# Steganalysis: no stego key, no public key, just the file", scan_log)
    got = gui.scan(legacy)
    s1 = gui.shot("S1_steganalysis_v1_found", 3)
    add_case("S1", "Steganalysis reads a version 1 payload without the key", legacy.as_posix(),
             "image", "Optional challenge: steganalysis", "Hidden Text Found", got.title(), log, [s1],
             "The structure scan finds the JSON, the LSB count and the location, and reads the "
             "message out.")
    got = gui.scan(FILES / "p1_image_stego.png")
    s2 = gui.shot("S2_steganalysis_v2_nothing", 3)
    add_case("S2", "Steganalysis finds nothing in a version 2 (masked) file",
             (FILES / "p1_image_stego.png").as_posix(), "image", "Our fix for S1",
             "Nothing Found", got.title(), log, [s2],
             "Masking the body with a key-derived stream removes the structure the scan relies on.")
    return adv


# --- LSB selection table ---

def lsb_table(cover_path, kind):
    cover = media.load_cover(cover_path)
    priv = crypto.load_private_key(PRIV)
    pub = crypto.load_public_key(PUB)
    rows = []
    for k in range(1, 9):
        stego, _, info = protect.protect(cover, cover_path.name, messages.LONG, k, KEY, priv)
        replay.clear()
        verdict = protect.verify(stego, KEY, pub).verdict
        changed = int(np.count_nonzero(cover.carrier != stego.carrier))
        if kind == "image":
            err = np.mean((cover.data.astype(float) - stego.data.astype(float)) ** 2)
            quality = f"PSNR {10 * np.log10(255 ** 2 / err):.1f} dB"
        else:
            s = cover.data.view("<i2").astype(float)
            n = stego.data.view("<i2").astype(float) - s
            quality = f"SNR {10 * np.log10(np.sum(s ** 2) / np.sum(n ** 2)):.1f} dB"
        rows.append({"k": k, "capacity": protect.capacity_bytes(cover, k), "body": info["body_len"],
                     "used_pct": round(info["percent_used"], 3), "changed": changed,
                     "quality": quality, "verdict": verdict})
        if kind == "image" and k in (1, 8):
            Image.fromarray(visual.difference(cover, stego)).save(SHOTS / f"lsb_k{k}_difference.png")
    return rows


# --- main ---

def main():
    for d in (FILES, LOGS, SHOTS):
        shutil.rmtree(d, ignore_errors=True)
        d.mkdir(parents=True)
    print("Generating evidence into", OUT.as_posix())

    with attacks.scratch_replay_store():
        make_inputs()
        gui = Gui()
        image_cover, audio_cover = FILES / "image_cover.png", FILES / "audio_cover.wav"

        p1 = positive(gui, "P1", "Image, short message (learning outcome), 2 LSBs", image_cover,
                      "image", "Short (learning outcome)", 2, "p1_image_stego.png",
                      "Positive image case, short payload")
        p2 = positive(gui, "P2", "Audio, long message (project overview), 2 LSBs", audio_cover,
                      "audio", "Long (project overview)", 2, "p2_audio_stego.wav",
                      "Positive audio case, long payload")
        positive(gui, "P3", "Image, custom payload encrypted with AES-GCM, 3 LSBs", image_cover,
                 "image", "Custom", 3, "p3_image_custom_encrypted.png",
                 "Custom payload: confidentiality + integrity")
        positive(gui, "P4", "Audio, custom encrypted payload, 8 LSBs", audio_cover,
                 "audio", "Custom", 8, "p4_audio_custom_k8.wav",
                 "Positive audio case at the LSB extreme")

        negative_cases(gui, p1, p2)
        advanced = advanced_cases(gui, image_cover)

        # the innovation: every attack against one image and one audio file
        attack_results = {}
        for kind, path in (("image", p1), ("audio", p2)):
            rows = attacks.run_all(media.load_cover(path), KEY, crypto.load_public_key(PUB))
            attack_results[kind] = [{"name": r.name, "what": r.what, "expected": list(r.expected),
                                     "got": r.got, "passed": r.passed, "reason": r.reason}
                                    for r in rows]
            gui.attack_lab(path)
            gui.shot(f"attack_lab_{kind}", 2)
            caught = sum(r.passed for r in rows)
            print(f"  Attack Lab on {kind}: {caught}/{len(rows)} caught")
        write_log("attack_lab", json.dumps(attack_results, indent=2))

        lsb = {"image": lsb_table(image_cover, "image"), "audio": lsb_table(audio_cover, "audio")}
        gui.win.close()

    # the full automated test suite, as its own log
    env = dict(os.environ, QT_QPA_PLATFORM="offscreen")
    tests = subprocess.run([sys.executable, "-m", "pytest", "-v", "-p", "no:cacheprovider"],
                           capture_output=True, text=True, env=env)
    (LOGS / "pytest.txt").write_text(tests.stdout + tests.stderr, encoding="utf-8")
    shutil.rmtree(".pytest-tmp", ignore_errors=True)
    summary = next((l.strip("= ") for l in reversed(tests.stdout.splitlines()) if "passed" in l), "?")
    print("  pytest:", summary)

    git = lambda *a: subprocess.run(["git", *a], capture_output=True, text=True).stdout.strip()
    results = {
        "team": "P6-4",
        "generated": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "commit": git("rev-parse", "--short", "HEAD"),
        "branch": git("branch", "--show-current"),
        "environment": {
            "python": platform.python_version(),
            "os": f"{platform.system()} {platform.release()}",
            "packages": {m: __import__(m).__version__ for m in
                         ("PySide6", "numpy", "PIL", "cryptography", "matplotlib")},
        },
        "stego_key": KEY,
        "cases": cases,
        "attacks": attack_results,
        "lsb_table": lsb,
        "pytest": summary,
        "advanced": advanced,
        "a_to_b": {name: sha256(FILES / name) for name in ("p1_image_stego.png", "p2_audio_stego.wav")},
    }
    (OUT / "results.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    bad = [c["id"] for c in cases if not c["passed"]]
    print("Done." if not bad else f"Done, but these cases didn't match: {bad}")


if __name__ == "__main__":
    main()
