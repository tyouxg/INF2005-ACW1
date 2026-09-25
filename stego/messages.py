"""Preset messages for the payload-size cases the spec asks for."""

SHORT = ("Explain how steganography can be used to embed hidden verification data "
         "in image and audio cover objects.")

LONG = ("This undergraduate project requires student teams to design, implement and "
        "demonstrate a GUI-based LSB Replacement steganography program (window-based or "
        "web-based) that protects and verifies both image and audio cover objects using "
        "steganography, hashing and digital signatures. The project focuses on practical "
        "cybersecurity concepts: hiding a verification payload inside an image and an audio "
        "file, signing relevant verification data, extracting the hidden payload, checking "
        "the digital signature, and demonstrating positive and negative verification cases. "
        "Video as a cover object is not required for the main assignment, but may be "
        "attempted as an optional challenge.")

# The team should swap this for their own custom payload. It's meant to be sent
# with encryption on, so it stays confidential as well as integrity-protected.
CUSTOM = "Donor match confirmed for patient P-4471, transplant scheduled 5 Oct 06:00. Details restricted to surgical team only."

PRESETS = {"Short (learning outcome)": SHORT, "Long (project overview)": LONG, "Custom": CUSTOM}
