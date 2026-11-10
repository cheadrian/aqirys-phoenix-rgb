# AQIRYS Phoenix RGB control (Windows)

Control the RGB lighting of the **AQIRYS Phoenix** gaming mouse
(USB `04D9:A09F`, Holtek MCU, PixArt 3327 sensor) without the vendor software,
and make it follow **Windows 11 Dynamic Lighting**.

The protocol was reverse-engineered from the official *AQIRYS Phoenix Software*
for interoperability. No vendor files are included.

| Script | What it does |
|---|---|
| `aqirys_phoenix_test.py` | Command-line tool: set the lighting mode, colours, brightness, speed and the logo / scroll-wheel colour. |
| `aqirys_dynamic_lighting.py` | Background bridge: watches the Windows Dynamic Lighting settings and applies the closest hardware effect to the mouse. |
| `startup.ps1` | Starts the bridge automatically at logon (or removes it). |

## Requirements

- Windows 10/11 (tested on **Windows 11 Pro, build 26300**)
- **Python 3** (tested with **Python 3.15.2**, 64-bit).
  No extra packages: the scripts use the built-in Windows HID API through `ctypes`.
- **Fully close the AQIRYS software** (including the tray icon) before using
  these scripts, otherwise the two programs fight over the mouse.

## Installation

1. Install Python 3 from <https://www.python.org/downloads/>
   (or `winget install Python.Python.3`). Make sure `python` works in a terminal.
2. Download this repository (green **Code → Download ZIP** button, then extract)
   or clone it:
   ```
   git clone https://github.com/cheadrian/aqirys-phoenix-rgb.git
   cd aqirys-phoenix-rgb
   ```
3. Check that the mouse is detected:
   ```
   python aqirys_phoenix_test.py --list
   ```
   You should see an interface with `usage_page=0xFF00 usage=0xFF00`.

## Usage: `aqirys_phoenix_test.py`

```
python aqirys_phoenix_test.py --mode static --color 00ff00
python aqirys_phoenix_test.py --mode breathing --color ff0000 --color 0000ff --speed 7
python aqirys_phoenix_test.py --mode wave --brightness 200 --speed 5
python aqirys_phoenix_test.py --mode static --color 00ff00 --dpi-color blue
python aqirys_phoenix_test.py --dpi-color red --dpi-color green --dpi-color blue
python aqirys_phoenix_test.py --mode off
```

| Option | Meaning |
|---|---|
| `--mode` | `off`, `static`, `blink`, `breathing`, `neon`, `wave`, `glide`, `click`, `aurora`, `yoyo`, `strobe` |
| `--color RRGGBB` | Side LED colour; repeat up to 8 times for multi-colour effects |
| `--brightness 0-255` | Side LED brightness (default 255) |
| `--speed 1-10` | Effect speed (default 6) |
| `--dpi-color` | Logo / scroll-wheel colour, one per DPI level (repeat up to 8 times; one value = all levels). Only 8 colours exist: `red`, `green`, `blue`, `yellow`, `cyan`, `magenta`, `white`, `orange` (or `0`-`7`) |
| `--dry-run` | Print the packets, send nothing |
| `--list` | List the mouse's HID interfaces |

Settings are stored in the mouse's onboard memory and survive a reboot or a
different PC.

## Usage: `aqirys_dynamic_lighting.py` (Windows Dynamic Lighting)

The mouse firmware does not implement the HID LampArray standard, so it can
never appear as a device in *Settings → Personalization → Dynamic Lighting*.
Instead, this bridge reads the **global** Dynamic Lighting settings from the
registry (`HKCU\Software\Microsoft\Lighting`) and, whenever they change, puts
the mouse in the closest hardware effect:

| Dynamic Lighting effect | Mouse side LEDs | Logo / scroll wheel |
|---|---|---|
| Solid colour | Static (colour + brightness) | nearest of the 8 colours |
| Breathing | Breathing | nearest colour |
| Rainbow | Wave (rainbow) | unchanged |
| Wave | Yo-Yo (colour 1 + colour 2) | nearest colour |
| Wheel | Neon (colour cycle) | unchanged |
| Gradient | Breathing (colour 1 + colour 2) | nearest colour |
| Brightness 0 / Dynamic Lighting off | Off | unchanged (cannot be switched off) |

"Match my Windows accent color" is supported. The mouse animates the effect
itself, so the bridge writes to it **only when a setting changes** (after the
sliders stop moving for 1.5 s). The mapping can be edited in `EFFECT_MAP` at
the top of the script.

```
python aqirys_dynamic_lighting.py            # run in a console (Ctrl+C to stop)
python aqirys_dynamic_lighting.py --once     # apply the current settings and exit
python aqirys_dynamic_lighting.py --dry-run  # show what would be sent
pythonw aqirys_dynamic_lighting.py --quiet   # run hidden, no console
```

## Run at startup

From the repository folder, in PowerShell:

```
powershell -ExecutionPolicy Bypass -File .\startup.ps1
```

This creates a shortcut *AQIRYS Dynamic Lighting* in your Startup folder
(`Win+R` → `shell:startup`) that runs the bridge hidden with `pythonw.exe` at
every logon. No administrator rights are needed. Keep the repository folder
where it is: the shortcut points to it.

To remove it (and stop a running instance):

```
powershell -ExecutionPolicy Bypass -File .\startup.ps1 -Uninstall
```

Alternatively, create the shortcut yourself in `shell:startup` with the target:

```
pythonw.exe "C:\path\to\aqirys-phoenix-rgb\aqirys_dynamic_lighting.py" --quiet
```

## Limitations

- **Logo / scroll wheel**: they show the DPI-level colour, chosen from a fixed
  palette of 8 colours. The firmware offers no brightness control and no way
  to switch them off (tested).
- **Side LEDs**: one colour set for the whole strip; no per-LED control and no
  real-time ("direct") mode. Every change is written to onboard memory.
- The bridge follows the global Dynamic Lighting settings only. If a game or
  app takes over lighting through Dynamic Lighting, the mouse does not follow it.

## Protocol summary

- Vendor HID interface: usage page `0xFF00`, usage `0xFF00`.
- Commands: 8-byte feature report `[cmd, a1..a6, 0xFF - sum]`, obfuscated
  (byte permutation, XOR with a fixed key, 3-bit rotation, per-byte offset).
- `0x83` / `0x03`: read / write the config block (handshake before every apply).
- `0x0D mode, p1, p2`: lighting mode, brightness, speed.
- `0x10 page, len` + 32-byte output report: page 0/1 = 8 RGB colours,
  page 2 = one 4-bit palette index per DPI level (logo / scroll wheel).
  The firmware reloads page 2 only when a *changed* `0x0D` command arrives.

## Disclaimer

Unofficial project, not affiliated with AQIRYS. Use at your own risk.
