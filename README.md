# Audinux – Audipo-Like Audio Player (PyQt6, VLC, Pydub)

Audinux is a lightweight audio player for Linux (tested on Debian 12, including 32-bit)  
inspired by the **Audipo** app on Android.  
It is optimized for **very long recordings** (lectures, podcasts, audiobooks of 6+ hours).

---

## Installation (Debian 12 / Ubuntu 20.04+)

Make sure you have Python 3.9+ installed. Then install dependencies:

```bash
sudo apt update
sudo apt install ffmpeg python3-pip python3-pyqt6 python3-vlc libvlc-dev \
        python3-numpy python3-pydub python3-scipy vlc vlc-plugin-base
````

Clone this repository and install:

```bash
git clone https://github.com/yourusername/audinux.git
cd audinux
pip3 install -r requirements.txt   # optional if you maintain a requirements file
```

---

## Run

```bash
python3 main.py
```

---

## Features

* **Variable playback speed**: from 0.25x up to 4.0x, with **time-stretch** preserving pitch (libVLC `:audio-time-stretch`).
* **Multi-line waveform** with vertical scrolling and zoom controls.
* **Markers**: add named bookmarks, jump to them, or create a **loop A↔B** between two markers.
* **Playlists**: build and navigate through multiple audio files.
* **Persistent settings**: playback rate, zoom level, and last used folder are stored via `QSettings`.
* **Keyboard shortcuts** for fast navigation (see below).

---

## Keyboard Shortcuts

* **Space**: Play / Pause
* **S**: Stop
* **← / →**: Seek ±5 s (Ctrl: ±30 s, Shift: ±1 s)
* **+ / -** or **Z / X**: Zoom in/out
* **M**: Add marker
* **, / .**: Jump to previous / next marker
* **L**: Toggle loop A↔B (select two markers first)
* **Ctrl+O**: Open file
* **Ctrl+P**: Add file to playlist
* **Ctrl+↑ / ↓**: Increase / Decrease playback speed

---

## Notes

* Supported formats: **MP3, WAV, FLAC, OGG**
  (waveform extraction via Pydub/FFmpeg, playback via libVLC).
* Independent pitch shifting is **not implemented yet** (planned).
* The project is designed for **very long audio files** (lectures, audiobooks, podcasts).
* No need to launch VLC separately — Audinux uses libVLC directly.

---

## For Developers

Audinux is written in **Python 3 + PyQt6** with modular code:

* `AudioProcessor` → playback engine (libVLC).
* `WaveformWidget` → waveform visualization and interaction.
* `MarkersManager` → bookmark and loop support.
* `Playlist` → simple playlist handling.
* `AppSettings` → persistent settings via `QSettings`.

### Contributions welcome!

If you want to help:

* Implement **independent pitch shifting**.
* Improve **waveform rendering performance** (GPU, OpenGL, etc).
* Add **export/import of markers**.
* Package as a **.deb** or **Flatpak** for easier distribution.

Pull requests are encouraged!

---

God Bless You
