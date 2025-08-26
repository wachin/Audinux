# Audinux – Audipo-Like Player (PyQt6, VLC, pydub)

Reproductor de audio para Linux (Debian 12, 32‑bit incluido) inspirado en Audipo.
- Velocidad variable **0.25x–4.0x** manteniendo el **tono** (libVLC `:audio-time-stretch`).
- Waveform **multi‑línea** con scroll vertical y botones de **zoom**.
- **Marcadores** con nombres, salto y **bucle A↔B**.
- **Listas de reproducción**, atajos de teclado y **persistencia** con QSettings.

## Instalación en Debian 12

```bash
sudo apt update
sudo apt install python3-pip python3-pyqt6 python3-vlc libvlc-dev
sudo apt install ffmpeg  # pydub usa ffmpeg para decodificar

pip install PyQt6 python-vlc pydub numpy scipy


## Ejecutar

```bash
python3 main.py
```

## Atajos
- **Espacio**: Play/Pause
- **S**: Stop
- **←/→**: ±5 s (Ctrl: ±30 s, Shift: ±1 s)
- **+ / -** o **Z / X**: Zoom in/out
- **M**: Añadir marcador
- **, / .**: Ir a marcador anterior / siguiente
- **L**: Activar/Desactivar bucle A↔B (selecciona dos marcadores)
- **Ctrl+O**: Abrir archivo
- **Ctrl+P**: Añadir a playlist
- **Ctrl+↑/↓**: Aumentar/Disminuir velocidad

## Notas
- Formatos: MP3/WAV/FLAC/OGG (pydub/ffmpeg para waveform, libVLC para playback).
- Persistencia de marcadores en `miarchivo.ext.markers.json` junto al audio.
- **Pitch** independiente no implementado por defecto (ver comentarios en código).



