#!/usr/bin/env python3
"""
AQIRYS Phoenix (USB 04D9:A09F) - lighting control tool.

Protocol reverse-engineered from the official "AQIRYS Phoenix Software"
(MouseDriver.exe / MSDriver.dll, Nov 2020) for interoperability.

Requirements: none on Windows (uses the built-in Windows HID API through
ctypes). On Linux/macOS: pip install hidapi (untested).
IMPORTANT: fully close the AQIRYS software (tray icon too) before running.

Examples:
  python aqirys_phoenix_test.py --list
  python aqirys_phoenix_test.py --mode static --color 00ff00
  python aqirys_phoenix_test.py --mode breathing --color ff0000 --speed 7
  python aqirys_phoenix_test.py --mode wave --brightness 200 --speed 5
  python aqirys_phoenix_test.py --mode static --color 00ff00 --dpi-color blue
  python aqirys_phoenix_test.py --mode off
  python aqirys_phoenix_test.py --mode static --color 0000ff --dry-run
"""
import argparse
import functools
import sys
import time

VID, PID = 0x04D9, 0xA09F
USAGE_PAGE, USAGE = 0xFF00, 0xFF00      # vendor interface used by the app
KEY = b"FB1133"                          # "Password" from the app's Data.ini
ADD = (0x25, 0xF6, 0xE4, 0x76, 0x47, 0x54, 0xE6, 0x76)
DELAY = 0.02                             # the app sleeps 20 ms after each packet

# Firmware mode values (index of the radio button in the app).
MODES = {
    "off": 0, "static": 1, "blink": 2, "breathing": 3, "neon": 4,
    "wave": 5, "glide": 6, "click": 7, "aurora": 8, "yoyo": 9,
    "strobe": 10,
}
# Factory colour table (R, G, B), used when no colour is given.
DEFAULT_COLORS = [(255, 0, 0), (0, 255, 0), (0, 0, 255), (255, 255, 0),
                  (255, 0, 255), (0, 255, 255), (255, 128, 0), (255, 255, 255)]


# ------------------------------------------------------------------ cipher
def encrypt(p):
    b = bytearray([p[5], p[4], p[7], p[6], p[1], p[0], p[3], p[2]])
    for i in range(6):
        b[i + 1] ^= KEY[i]
    r = [((b[i] << 3) | (b[(i + 1) % 8] >> 5)) & 0xFF for i in range(8)]
    return bytes((r[i] + ADD[i]) & 0xFF for i in range(8))


def decrypt(c):
    r = [(c[i] - ADD[i]) & 0xFF for i in range(8)]
    b = bytearray(((r[i] >> 3) | (r[(i - 1) % 8] << 5)) & 0xFF for i in range(8))
    for i in range(6):
        b[i + 1] ^= KEY[i]
    p = bytearray(8)
    p[5], p[4], p[7], p[6], p[1], p[0], p[3], p[2] = b
    return bytes(p)


def packet(*body):
    """8-byte command: up to 7 bytes + checksum (0xFF - sum)."""
    b = list(body) + [0] * (7 - len(body))
    b.append((0xFF - sum(b)) & 0xFF)
    return bytes(b)


def checksum_ok(p):
    return (sum(p[:7]) + p[7]) & 0xFF == 0xFF


# -------------------------------------------------------------- transport
def hid_backend():
    """Native Windows HID API (no install needed); hidapi elsewhere."""
    if sys.platform == "win32":
        return WinHid
    try:
        import hid
        return hid
    except ImportError:
        sys.exit("Install hidapi first:  pip install hidapi")


class WinHid:
    """Minimal hidapi-compatible wrapper over hid.dll / setupapi.dll,
    doing the same calls as the vendor's MSDriver.dll."""

    @staticmethod
    @functools.lru_cache(maxsize=None)
    def _api():
        import ctypes
        from ctypes import wintypes as wt

        class GUID(ctypes.Structure):
            _fields_ = [("Data1", wt.DWORD), ("Data2", wt.WORD),
                        ("Data3", wt.WORD), ("Data4", ctypes.c_ubyte * 8)]

        class SP_DEVICE_INTERFACE_DATA(ctypes.Structure):
            _fields_ = [("cbSize", wt.DWORD), ("InterfaceClassGuid", GUID),
                        ("Flags", wt.DWORD), ("Reserved", ctypes.c_size_t)]

        class HIDD_ATTRIBUTES(ctypes.Structure):
            _fields_ = [("Size", wt.ULONG), ("VendorID", wt.USHORT),
                        ("ProductID", wt.USHORT), ("VersionNumber", wt.USHORT)]

        class HIDP_CAPS(ctypes.Structure):
            _fields_ = [("Usage", wt.USHORT), ("UsagePage", wt.USHORT),
                        ("InputReportByteLength", wt.USHORT),
                        ("OutputReportByteLength", wt.USHORT),
                        ("FeatureReportByteLength", wt.USHORT),
                        ("Reserved", wt.USHORT * 17),
                        ("Counts", wt.USHORT * 10)]

        hid = ctypes.WinDLL("hid")
        sa = ctypes.WinDLL("setupapi", use_last_error=True)
        k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        H = ctypes.c_void_p
        P = ctypes.c_void_p

        hid.HidD_GetHidGuid.argtypes = [ctypes.POINTER(GUID)]
        hid.HidD_GetAttributes.argtypes = [H, ctypes.POINTER(HIDD_ATTRIBUTES)]
        hid.HidD_GetAttributes.restype = ctypes.c_ubyte
        hid.HidD_GetPreparsedData.argtypes = [H, ctypes.POINTER(P)]
        hid.HidD_GetPreparsedData.restype = ctypes.c_ubyte
        hid.HidD_FreePreparsedData.argtypes = [P]
        hid.HidP_GetCaps.argtypes = [P, ctypes.POINTER(HIDP_CAPS)]
        hid.HidP_GetCaps.restype = ctypes.c_long
        hid.HidD_SetFeature.argtypes = [H, P, wt.ULONG]
        hid.HidD_SetFeature.restype = ctypes.c_ubyte
        hid.HidD_GetFeature.argtypes = [H, P, wt.ULONG]
        hid.HidD_GetFeature.restype = ctypes.c_ubyte
        sa.SetupDiGetClassDevsW.argtypes = [ctypes.POINTER(GUID), wt.LPCWSTR, wt.HWND, wt.DWORD]
        sa.SetupDiGetClassDevsW.restype = H
        sa.SetupDiEnumDeviceInterfaces.argtypes = [H, P, ctypes.POINTER(GUID), wt.DWORD,
                                                   ctypes.POINTER(SP_DEVICE_INTERFACE_DATA)]
        sa.SetupDiEnumDeviceInterfaces.restype = wt.BOOL
        sa.SetupDiGetDeviceInterfaceDetailW.argtypes = [H, ctypes.POINTER(SP_DEVICE_INTERFACE_DATA),
                                                        P, wt.DWORD, ctypes.POINTER(wt.DWORD), P]
        sa.SetupDiGetDeviceInterfaceDetailW.restype = wt.BOOL
        sa.SetupDiDestroyDeviceInfoList.argtypes = [H]
        k32.CreateFileW.argtypes = [wt.LPCWSTR, wt.DWORD, wt.DWORD, P, wt.DWORD, wt.DWORD, H]
        k32.CreateFileW.restype = H
        k32.WriteFile.argtypes = [H, P, wt.DWORD, ctypes.POINTER(wt.DWORD), P]
        k32.WriteFile.restype = wt.BOOL
        k32.CloseHandle.argtypes = [H]
        return ctypes, wt, hid, sa, k32, GUID, SP_DEVICE_INTERFACE_DATA, HIDD_ATTRIBUTES, HIDP_CAPS

    @staticmethod
    def _open(path, access):
        ctypes, wt, hid, sa, k32, *_ = WinHid._api()
        h = k32.CreateFileW(path, access, 0x1 | 0x2, None, 3, 0, None)  # share R|W, OPEN_EXISTING
        if h is None or h == ctypes.c_void_p(-1).value:
            return None
        return h

    @staticmethod
    def _caps(h):
        ctypes, wt, hid, sa, k32, GUID, IFD, ATTR, CAPS = WinHid._api()
        pp = ctypes.c_void_p()
        caps = CAPS()
        if hid.HidD_GetPreparsedData(h, ctypes.byref(pp)):
            hid.HidP_GetCaps(pp, ctypes.byref(caps))
            hid.HidD_FreePreparsedData(pp)
        return caps

    @staticmethod
    def enumerate(vid, pid):
        ctypes, wt, hid, sa, k32, GUID, IFD, ATTR, CAPS = WinHid._api()
        guid = GUID()
        hid.HidD_GetHidGuid(ctypes.byref(guid))
        info = sa.SetupDiGetClassDevsW(ctypes.byref(guid), None, None, 0x12)  # PRESENT|INTERFACE
        out = []
        i = 0
        while True:
            ifd = IFD()
            ifd.cbSize = ctypes.sizeof(IFD)
            if not sa.SetupDiEnumDeviceInterfaces(info, None, ctypes.byref(guid), i, ctypes.byref(ifd)):
                break
            i += 1
            need = wt.DWORD()
            sa.SetupDiGetDeviceInterfaceDetailW(info, ctypes.byref(ifd), None, 0, ctypes.byref(need), None)
            buf = ctypes.create_string_buffer(need.value + 4)
            ctypes.c_uint32.from_buffer(buf).value = 8 if ctypes.sizeof(ctypes.c_void_p) == 8 else 6
            if not sa.SetupDiGetDeviceInterfaceDetailW(info, ctypes.byref(ifd), buf, need.value + 4, None, None):
                continue
            path = ctypes.wstring_at(ctypes.addressof(buf) + 4)
            h = WinHid._open(path, 0)          # query-only access works for mice too
            if h is None:
                continue
            attr = ATTR()
            attr.Size = ctypes.sizeof(ATTR)
            ok = hid.HidD_GetAttributes(h, ctypes.byref(attr))
            if ok and attr.VendorID == vid and attr.ProductID == pid:
                caps = WinHid._caps(h)
                mi = path.lower().find("&mi_")
                out.append({"path": path, "usage_page": caps.UsagePage, "usage": caps.Usage,
                            "interface_number": int(path[mi + 4:mi + 6], 16) if mi >= 0 else -1,
                            "feature_len": caps.FeatureReportByteLength,
                            "output_len": caps.OutputReportByteLength})
            k32.CloseHandle(h)
        sa.SetupDiDestroyDeviceInfoList(info)
        return out

    class device:
        def open_path(self, path):
            self.h = WinHid._open(path, 0x80000000 | 0x40000000)   # GENERIC_READ|WRITE
            if self.h is None:
                sys.exit("Cannot open the mouse interface (is the AQIRYS software still running?)")
            caps = WinHid._caps(self.h)
            self.flen = caps.FeatureReportByteLength or 9
            self.olen = caps.OutputReportByteLength or 33

        def _buf(self, data, length):
            ctypes = WinHid._api()[0]
            b = bytes(data)[:length].ljust(length, b"\0")
            return ctypes.create_string_buffer(b, length)

        def send_feature_report(self, data):
            ctypes, wt, hid, *_ = WinHid._api()
            buf = self._buf(data, self.flen)
            if not hid.HidD_SetFeature(self.h, buf, self.flen):
                print(f"  ! HidD_SetFeature failed (error {ctypes.get_last_error()})")

        def get_feature_report(self, report_id, length):
            ctypes, wt, hid, *_ = WinHid._api()
            buf = self._buf([report_id], self.flen)
            if not hid.HidD_GetFeature(self.h, buf, self.flen):
                print(f"  ! HidD_GetFeature failed (error {ctypes.get_last_error()})")
            return list(buf.raw[:max(length, 9)])

        def write(self, data):
            ctypes, wt, hid, sa, k32, *_ = WinHid._api()
            buf = self._buf(data, self.olen)
            n = wt.DWORD()
            if not k32.WriteFile(self.h, buf, self.olen, ctypes.byref(n), None):
                print(f"  ! WriteFile failed (error {ctypes.get_last_error()})")

        def close(self):
            if getattr(self, "h", None) is not None:
                WinHid._api()[4].CloseHandle(self.h)
                self.h = None


class Mouse:
    def __init__(self, dry_run=False, encrypted=True):
        self.dry = dry_run
        self.enc = encrypted
        self.dev = None
        if not dry_run:
            hid = hid_backend()
            path = None
            for d in hid.enumerate(VID, PID):
                if d["usage_page"] == USAGE_PAGE and d["usage"] == USAGE:
                    path = d["path"]
            if path is None:
                sys.exit("Interface FF00/FF00 not found. Mouse plugged in? Run --list.")
            self.dev = hid.device()
            self.dev.open_path(path)

    def set_feature(self, pkt, label):
        wire = encrypt(pkt) if self.enc else pkt
        print(f"  SET  {label:<14} plain={pkt.hex(' ')}  wire={wire.hex(' ')}")
        if not self.dry:
            self.dev.send_feature_report([0x00] + list(wire))
        time.sleep(DELAY)

    def get_feature(self, label):
        if self.dry:
            print(f"  GET  {label:<14} (dry run)")
            return None
        data = bytes(self.dev.get_feature_report(0x00, 9))
        wire = data[1:9] if len(data) >= 9 else data[:8]
        plain = decrypt(wire) if self.enc else wire
        print(f"  GET  {label:<14} wire={wire.hex(' ')}  plain={plain.hex(' ')}")
        return plain

    def write(self, data32, label):
        print(f"  OUT  {label:<14} {bytes(data32[:24]).hex(' ')}")
        if not self.dry:
            self.dev.write([0x00] + list(data32))
        time.sleep(DELAY)

    def close(self):
        if self.dev is not None and hasattr(self.dev, "close"):
            self.dev.close()
        self.dev = None


# -------------------------------------------------------------- protocol
def mode_bytes(mode, brightness, speed):
    """Bytes 2 and 3 of command 0x0D, exactly as the official app builds them."""
    br = brightness & 0xFF
    if mode == 0:  return 0, 0
    if mode == 1:  return br, 0xFF          # app default for "frequency 1"
    if mode == 2:  return br, 0
    if mode in (3, 4): return 0, 11 - speed  # speed 1..10
    if mode == 5:  return br, 11 - speed     # speed 1..10
    if mode == 6:  return 0, 0
    if mode == 7:  return br, 0
    if mode == 8:  return br, 20 - speed     # speed 0..10
    if mode == 9:  return br, 15 - speed     # speed 0..10
    if mode == 10: return br, 30 - speed     # speed 0..10
    raise ValueError(mode)


def color_page(page, colors):
    """Command 0x10: write 24 bytes (8 x RGB) to colour page 0 or 1."""
    data = bytearray(32)
    for i in range(8):
        r, g, b = colors[i % len(colors)]
        data[i * 3:i * 3 + 3] = bytes((r, g, b))
    return packet(0x10, page, 0x18), data


# Fixed DPI-indicator palette (logo + scroll wheel) when Data.ini has
# DPIColorType=2. Index order from MouseDriver.exe @0x41560a.
DPI_PALETTE = ["red", "green", "blue", "yellow", "cyan", "magenta", "white", "orange"]


# Hue ranges (upper bound in degrees -> palette index); yellow and cyan are
# narrow on real LEDs. White (6) is handled apart.
DPI_HUE_BANDS = [(15, 0), (45, 7), (75, 3), (165, 1), (195, 4), (270, 2), (345, 5), (360, 0)]


def nearest_dpi_color(rgb):
    """Closest DPI palette index by hue (RGB distance picks orange for
    reddish colours like #E74856). Low saturation -> white."""
    r, g, b = rgb
    mx, mn = max(rgb), min(rgb)
    if mx == 0 or (mx - mn) * 4 < mx:          # saturation < 25 %
        return 6
    d = mx - mn
    if mx == r:
        h = 60 * ((g - b) / d)
    elif mx == g:
        h = 60 * ((b - r) / d + 2)
    else:
        h = 60 * ((r - g) / d + 4)
    h %= 360
    return next(idx for top, idx in DPI_HUE_BANDS if h < top)


def dpi_color_page(indices):
    """Command 0x10 page 2 (len 4): one nibble per DPI level (8 levels),
    byte k = idx[2k+1] << 4 | idx[2k]. Each nibble picks a DPI_PALETTE entry."""
    idx = [indices[i % len(indices)] & 0x0F for i in range(8)]
    data = bytearray(32)
    for k in range(4):
        data[k] = (idx[2 * k + 1] << 4) | idx[2 * k]
    return packet(0x10, 0x02, 0x04), data


def parse_dpi_color(s):
    s = s.lower()
    if s in DPI_PALETTE:
        return DPI_PALETTE.index(s)
    if s.isdigit() and 0 <= int(s) <= 7:
        return int(s)
    raise argparse.ArgumentTypeError(f"use 0-7 or one of {', '.join(DPI_PALETTE)}")


def handshake_seq(m):
    m.set_feature(packet(0x83), "read cfg 0x83")
    resp = m.get_feature("response")
    # The reply has no checksum; the mouse echoes the command in byte 0.
    if resp is not None and resp[0] == 0x83:
        r = bytearray(resp)
        r[0] = 0x03
        r[4] |= 0x40
        m.set_feature(packet(*r[:7]), "write 0x03")
    elif resp is not None:
        print("  ! unexpected reply (no 0x83 echo) -> skipping 0x03 (safe)")


def apply_dpi_colors(m, indices):
    cmd, data = dpi_color_page(indices)
    m.set_feature(cmd, "dpi colours p2")
    m.write(data, "dpi idx p2")


def apply(m, mode, colors, brightness, speed, handshake=True, dpi=None):
    """Vendor order: 0x0D, page 0, page 1, page 2.  With dpi (list of palette
    indices) page 2 is written too, then 0x0D is re-sent with a tweaked and
    then the real parameter: the firmware only reloads the logo/scroll colour
    when the light-mode command CHANGES (confirmed on hardware)."""
    if handshake:
        handshake_seq(m)

    b2, b3 = mode_bytes(mode, brightness, speed)
    m.set_feature(packet(0x0D, mode, b2, b3), "light mode")

    for page in (0, 1):   # page 0 = loop colours, page 1 = glide colours
        cmd, data = color_page(page, colors)
        m.set_feature(cmd, f"colour page {page}")
        m.write(data, f"colours p{page}")

    if dpi:
        apply_dpi_colors(m, dpi)
        m.set_feature(packet(0x0D, mode, b2 ^ 0x01, b3), "mode (refresh)")
        m.set_feature(packet(0x0D, mode, b2, b3), "light mode")


def parse_color(s):
    s = s.lstrip("#")
    return tuple(int(s[i:i + 2], 16) for i in (0, 2, 4))


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--list", action="store_true", help="list HID interfaces of the mouse")
    ap.add_argument("--mode", choices=MODES.keys())
    ap.add_argument("--color", action="append",
                    help="RRGGBB, can be repeated up to 8 times (default: factory palette)")
    ap.add_argument("--brightness", type=int, default=255, help="0-255 (default 255)")
    ap.add_argument("--speed", type=int, default=6, help="1-10 (default 6)")
    ap.add_argument("--dpi-color", action="append", type=parse_dpi_color,
                    help="logo/scroll colour per DPI level: 0-7 or "
                         + "/".join(DPI_PALETTE) + "; repeat up to 8 times "
                         "(one value = all levels). Works with or without --mode.")
    ap.add_argument("--dry-run", action="store_true", help="print packets, do not send")
    ap.add_argument("--no-handshake", action="store_true",
                    help="skip the 0x83/read/0x03 sequence")
    ap.add_argument("--no-encryption", action="store_true",
                    help="send packets unencrypted (only for experiments)")
    a = ap.parse_args()

    if a.list:
        hid = hid_backend()
        print("(HID backend: %s)" % ("Windows HID API" if hid is WinHid else "hidapi"))
        for d in hid.enumerate(VID, PID):
            print(f"iface={d['interface_number']} usage_page=0x{d['usage_page']:04X} "
                  f"usage=0x{d['usage']:04X} path={d['path']}")
        return
    if not a.mode and not a.dpi_color:
        ap.error("--mode and/or --dpi-color is required (or use --list)")
    if a.dpi_color and len(a.dpi_color) > 8:
        ap.error("--dpi-color: at most 8 values")

    m = Mouse(dry_run=a.dry_run, encrypted=not a.no_encryption)
    if a.mode:
        mode = MODES[a.mode]
        speed = max(1 if mode in (3, 4, 5) else 0, min(10, a.speed))
        colors = [parse_color(c) for c in a.color] if a.color else DEFAULT_COLORS
        print(f"Mode {a.mode} ({mode}), brightness {a.brightness}, speed {speed}, "
              f"colours {['%02x%02x%02x' % c for c in colors]}")
        if a.dpi_color:
            print(f"DPI colours (logo/scroll): {[DPI_PALETTE[i] for i in a.dpi_color]}")
        apply(m, mode, colors, max(0, min(255, a.brightness)), speed,
              handshake=not a.no_handshake, dpi=a.dpi_color)
    else:
        # Page 2 only: the logo picks it up at the next DPI / mode change.
        if not a.no_handshake:
            handshake_seq(m)
        print(f"DPI colours (logo/scroll): {[DPI_PALETTE[i] for i in a.dpi_color]}")
        apply_dpi_colors(m, a.dpi_color)
    print("Done.")


if __name__ == "__main__":
    main()
