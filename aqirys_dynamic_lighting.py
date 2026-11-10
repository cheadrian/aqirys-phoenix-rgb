#!/usr/bin/env python3
"""
AQIRYS Phoenix <- Windows Dynamic Lighting bridge.

The mouse firmware has no HID LampArray, so Windows cannot drive it directly.
This tool watches the global Dynamic Lighting settings
(HKCU\\Software\\Microsoft\\Lighting) and, whenever they change, puts the
mouse in the closest HARDWARE effect. The mouse animates by itself, so it is
written to only when a setting changes (onboard memory is not worn out).

  Windows effect     -> mouse side LEDs              logo / scroll wheel
  Solid colour       -> Static (Color, brightness)   nearest palette colour
  Breathing          -> Breathing (Color)            nearest palette colour
  Rainbow            -> Wave (rainbow)               unchanged
  Wave               -> Yo-Yo (Color, Color2)        nearest palette colour
  Wheel              -> Neon (colour cycle)          unchanged
  Gradient           -> Breathing (Color, Color2)    nearest palette colour
  brightness 0 / Dynamic Lighting turned off -> side LEDs Off
  (the logo/scroll LED cannot be switched off by the firmware)

Edit EFFECT_MAP below to change the mapping.

Usage (AQIRYS software must be closed):
  python aqirys_dynamic_lighting.py              # run in foreground
  pythonw aqirys_dynamic_lighting.py --quiet     # run hidden (e.g. at logon)
  python aqirys_dynamic_lighting.py --once       # apply current settings, exit
  python aqirys_dynamic_lighting.py --dry-run    # show what would be sent
"""
import argparse
import sys
import time
import winreg

import aqirys_phoenix_test as aq

LIGHTING_KEY = r"Software\Microsoft\Lighting"
ACCENT_KEY = r"Software\Microsoft\Windows\DWM"
POLL = 0.5          # seconds between registry reads
SETTLE = 1.5        # wait until settings stop changing (slider drags)

# Windows EffectType -> (mouse mode, colour source, follow DPI colour)
#   colour source: "c1" = Color, "c12" = Color + Color2, None = factory palette
EFFECT_MAP = {
    0: ("static",    "c1",  True),    # Solid colour
    1: ("breathing", "c1",  True),    # Breathing
    2: ("wave",      None,  False),   # Rainbow
    4: ("yoyo",      "c12", True),    # Wave
    5: ("neon",      None,  False),   # Wheel
    6: ("breathing", "c12", True),    # Gradient
}
DEFAULT_EFFECT = ("static", "c1", True)


def read_values(path):
    out = {}
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, path) as k:
            i = 0
            while True:
                try:
                    name, value, _ = winreg.EnumValue(k, i)
                except OSError:
                    break
                out[name] = value
                i += 1
    except OSError:
        pass
    return out


def abgr_to_rgb(v):
    """Dynamic Lighting stores Color/Color2 as 0xAABBGGRR (like COLORREF):
    e.g. FF00B9FF is the Windows swatch #FFB900."""
    v &= 0xFFFFFFFF
    return (v & 0xFF, (v >> 8) & 0xFF, (v >> 16) & 0xFF)


def accent_rgb():
    """Windows accent colour (DWM AccentColor is 0xAABBGGRR)."""
    v = read_values(ACCENT_KEY).get("AccentColor")
    if not isinstance(v, int):
        return None
    v &= 0xFFFFFFFF
    return (v & 0xFF, (v >> 8) & 0xFF, (v >> 16) & 0xFF)


def nearest_palette(rgb):
    return aq.nearest_dpi_color(rgb)


def target_state(s):
    """Translate Dynamic Lighting settings into a mouse state (hashable)."""
    enabled = s.get("AmbientLightingEnabled", 1)
    brightness = max(0, min(100, int(s.get("Brightness", 100))))
    speed = max(1, min(10, int(s.get("Speed", 5))))
    c1 = abgr_to_rgb(s.get("Color", 0xFFFFFFFF))
    c2 = abgr_to_rgb(s.get("Color2", 0xFFFFFFFF))
    if s.get("UseSystemAccentColor", 0):
        c1 = accent_rgb() or c1

    mode, src, follow_dpi = EFFECT_MAP.get(s.get("EffectType", 0), DEFAULT_EFFECT)
    if not enabled or brightness == 0:
        mode, src = "off", None

    colors = ((c1,) if src == "c1" else (c1, c2) if src == "c12" else None)
    dpi = nearest_palette(c1) if follow_dpi else None
    return (mode, round(brightness * 255 / 100), speed, colors, dpi)


def describe(st):
    mode, br, speed, colors, dpi = st
    cs = ",".join("%02x%02x%02x" % c for c in colors) if colors else "factory"
    d = aq.DPI_PALETTE[dpi] if dpi is not None else "unchanged"
    return f"{mode} brightness={br} speed={speed} colours={cs} logo={d}"


def apply_state(st, dry_run, quiet):
    mode, br, speed, colors, dpi = st
    out = sys.stdout
    if quiet:
        sys.stdout = open("nul", "w")
    try:
        m = aq.Mouse(dry_run=dry_run)
    except SystemExit as e:
        sys.stdout = out
        print(time.strftime("%H:%M:%S"), "mouse not available:", e)
        return False
    try:
        aq.apply(m, aq.MODES[mode], list(colors) if colors else aq.DEFAULT_COLORS, br, speed,
                 dpi=[dpi] if dpi is not None else None)
    finally:
        m.close()
        if quiet:
            sys.stdout.close()
            sys.stdout = out
    return True


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--once", action="store_true", help="apply current settings and exit")
    ap.add_argument("--dry-run", action="store_true", help="do not send anything to the mouse")
    ap.add_argument("--quiet", action="store_true", help="do not print packets")
    a = ap.parse_args()

    if sys.stdout is None:              # pythonw: no console
        import os
        sys.stdout = sys.stderr = open(os.devnull, "w")

    applied = None
    pending, changed_at = None, 0.0
    retry_at = 0.0
    print("Watching Dynamic Lighting settings (Ctrl+C to stop)...")
    while True:
        st = target_state(read_values(LIGHTING_KEY))
        if st != pending:
            pending, changed_at, retry_at = st, time.time(), 0.0
        now = time.time()
        if (pending != applied and now >= retry_at
                and (applied is None or now - changed_at >= SETTLE)):
            print(time.strftime("%H:%M:%S"), "->", describe(pending))
            if apply_state(pending, a.dry_run, a.quiet):
                applied = pending
            else:
                retry_at = now + 5      # mouse unplugged / busy: retry later
            if a.once:
                return
        time.sleep(POLL)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass
