# AQIRYS Phoenix RGB – notes for Claude

Python tools for the AQIRYS Phoenix mouse (USB `04D9:A09F`) on Windows.
The user speaks Romanian; reply in Romanian.

## Files
- `aqirys_phoenix_test.py` – CLI and protocol library (cipher, packets,
  Windows HID via ctypes, no pip packages). The bridge imports it, so keep the name.
- `aqirys_dynamic_lighting.py` – polls `HKCU\Software\Microsoft\Lighting` and
  maps Dynamic Lighting effects to hardware modes (`EFFECT_MAP`).
- `startup.ps1` – Startup-folder shortcut (pythonw, `--quiet`); `-Uninstall`.

## Protocol facts (verified on hardware)
- Feature report 8 bytes, checksum `0xFF - sum`, then obfuscated (key `FB1133`).
- Handshake: `0x83` → reply echoes `0x83` (no checksum) → `0x03` with byte4 |= 0x40.
- `0x0D mode p1 p2`; pages via `0x10 page len` + 32-byte output report.
- Page 2 = logo/scroll colour: 4-bit index per DPI level, fixed palette
  red, green, blue, yellow, cyan, magenta, white, orange. It is applied only
  when `0x0D` CHANGES, so re-send `0x0D` with p1^1 and then the real value.
- Logo/scroll cannot be dimmed or turned off (tested: 0x0D bytes 4–6,
  indices 8–15, config bits). Config byte1 ≠ 0 freezes the cursor: do not touch it.
- Dynamic Lighting `Color`/`Color2` are ABGR. EffectType: 0 Solid,
  1 Breathing, 2 Rainbow, 4 Wave, 5 Wheel, 6 Gradient. Brightness 0–100, Speed 1–10.

## Constraints
- Settings go to onboard memory: no real-time/direct streaming, write only on change.
- Tested with Python 3.15.2 on Windows 11. The vendor app must be closed.
