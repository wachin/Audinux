#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Audinux - Reproductor de audio para Linux inspirado en Audipo
Optimizado para archivos largos (6+ horas)
"""

import os
import sys
import json
import vlc
import numpy as np
from dataclasses import dataclass
from typing import List, Optional, Tuple, Dict
from PyQt6.QtCore import Qt, QTimer, QSettings, QRect, QSize, pyqtSignal
from PyQt6.QtGui import QPainter, QPen, QPainterPath
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QSlider, QFileDialog, QScrollArea, 
    QListWidget, QListWidgetItem, QSplitter, QLineEdit, QMessageBox
)

from pydub import AudioSegment

# Constantes y funciones auxiliares
MARKERS_SUFFIX = ".markers.json"

def markers_path_for(audio_path: str) -> str:
    return f"{audio_path}{MARKERS_SUFFIX}"

def load_json(path: str, default):
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return default

def save_json(path: str, data) -> bool:
    try:
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return True
    except Exception:
        return False

def fmt_ms(ms: int) -> str:
    total_seconds = int(ms // 1000)
    ms_part = int(ms % 1000)
    h = total_seconds // 3600
    m = (total_seconds % 3600) // 60
    s = total_seconds % 60
    if h:
        return f"{h:02d}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"

# Clase para manejo de configuraciones
class AppSettings:
    def __init__(self):
        self.s = QSettings("Audinux", "AudinuxPlayer")

    def get(self, key: str, default=None):
        return self.s.value(key, default)

    def set(self, key: str, value):
        self.s.setValue(key, value)

    def last_dir(self) -> str:
        return self.get('last_dir', '')

    def set_last_dir(self, path: str):
        self.set('last_dir', path)

    def last_rate(self) -> float:
        return float(self.get('last_rate', 1.0))

    def set_last_rate(self, r: float):
        self.set('last_rate', r)

    def zoom_level(self) -> float:
        return float(self.get('zoom', 1.0))

    def set_zoom_level(self, z: float):
        self.set('zoom', z)

# Clase para manejo de marcadores
@dataclass
class Marker:
    name: str
    ms: int

class MarkersManager:
    def __init__(self):
        self._markers: List[Marker] = []
        self._audio_path: Optional[str] = None
        self.loop_enabled = False
        self.loop_start: Optional[int] = None
        self.loop_end: Optional[int] = None

    def load_for(self, audio_path: str):
        self._audio_path = audio_path
        data = load_json(markers_path_for(audio_path), [])
        self._markers = [Marker(m.get('name', ''), int(m.get('ms', 0))) for m in data]

    def save(self):
        if not self._audio_path:
            return False
        data = [m.__dict__ for m in self._markers]
        return save_json(markers_path_for(self._audio_path), data)

    def add_marker(self, position_ms: int, name: str):
        self._markers.append(Marker(name=name, ms=int(position_ms)))
        self._markers.sort(key=lambda m: m.ms)
        self.save()

    def list(self) -> List[Marker]:
        return list(self._markers)

    def clear(self):
        self._markers.clear()
        self.save()

    def nearest_before(self, ms: int) -> Optional[Marker]:
        prev = [m for m in self._markers if m.ms < ms]
        return prev[-1] if prev else None

    def nearest_after(self, ms: int) -> Optional[Marker]:
        nxt = [m for m in self._markers if m.ms > ms]
        return nxt[0] if nxt else None

    def set_loop(self, start_ms: Optional[int], end_ms: Optional[int]):
        self.loop_start = start_ms
        self.loop_end = end_ms
        self.loop_enabled = start_ms is not None and end_ms is not None and start_ms < end_ms

    def should_loop(self, current_ms: int) -> Optional[int]:
        if self.loop_enabled and self.loop_start is not None and self.loop_end is not None:
            if current_ms >= self.loop_end:
                return int(self.loop_start)
        return None

# Clase para manejo de listas de reproducción
class Playlist:
    def __init__(self):
        self.items: List[str] = []
        self.index = -1

    def add(self, path: str):
        self.items.append(path)
        if self.index == -1:
            self.index = 0

    def current(self) -> str | None:
        if 0 <= self.index < len(self.items):
            return self.items[self.index]
        return None

    def next(self) -> str | None:
        if self.index + 1 < len(self.items):
            self.index += 1
            return self.items[self.index]
        return None

    def prev(self) -> str | None:
        if self.index - 1 >= 0:
            self.index -= 1
            return self.items[self.index]
        return None

    def all(self) -> List[str]:
        return list(self.items)

# Clase para procesamiento de audio optimizada
class AudioProcessor:
    def __init__(self):
        # Inicializar VLC con opciones específicas para Linux
        self.instance = vlc.Instance([
            '--no-video', 
            '--quiet', 
            '--intf', 'dummy', 
            '--no-xlib',
            '--aout=alsa',  # Usar ALSA para audio en Linux
            '--audio-time-stretch'  # Habilitar time-stretch
        ])
        self.player: vlc.MediaPlayer = self.instance.media_player_new()
        self.media: Optional[vlc.Media] = None
        self.audio_path: Optional[str] = None
        self.duration_ms: int = 0
        self.sample_rate: int = 0
        
        # Establecer volumen inicial
        self.player.audio_set_volume(70)
        
        # Configurar manejadores de eventos
        self.event_manager = self.player.event_manager()
        self.event_manager.event_attach(vlc.EventType.MediaPlayerPlaying, self._on_playing)
        self.event_manager.event_attach(vlc.EventType.MediaPlayerEncounteredError, self._on_error)
        
        self.is_ready = False

    def _on_playing(self, event):
        print("Reproduciendo audio")
        self.is_ready = True

    def _on_error(self, event):
        print("Error en reproducción de audio")
        self.is_ready = False

    def load_audio(self, file_path: str):
        if not os.path.exists(file_path):
            raise FileNotFoundError(file_path)
        
        print(f"Cargando archivo: {file_path}")
        self.audio_path = file_path
        self.media = self.instance.media_new_path(file_path)
        
        # Asegurar que el time-stretch esté habilitado
        self.media.add_option(':audio-time-stretch')
        
        self.player.set_media(self.media)
        
        # Parsear el medio para obtener metadatos
        self.media.parse_with_options(vlc.MediaParseFlag.local, 0)
        
        # Obtener duración
        dur = self.media.get_duration()
        if dur and dur > 0:
            self.duration_ms = int(dur)
            print(f"Duración detectada: {self.duration_ms} ms")
        else:
            # Fallback con pydub
            seg = AudioSegment.from_file(file_path)
            self.duration_ms = len(seg)
            print(f"Duración fallback: {self.duration_ms} ms")
        
        # Cargar información básica del audio
        self._load_audio_info(file_path)
        
        # Marcar como listo
        self.is_ready = True
        print("Audio cargado correctamente")

    def _load_audio_info(self, file_path: str):
        try:
            seg: AudioSegment = AudioSegment.from_file(file_path)
            self.sample_rate = seg.frame_rate
            print(f"Información de audio cargada: {self.sample_rate} Hz")
        except Exception as e:
            print(f"Error al cargar información de audio: {e}")
            self.sample_rate = 44100  # Valor por defecto

    def get_waveform_segment(self, start_ms: int, end_ms: int, resolution: int) -> Tuple[np.ndarray, np.ndarray]:
        """Obtener un segmento de la forma de onda con la resolución especificada"""
        if not self.audio_path or not os.path.exists(self.audio_path):
            return np.array([]), np.array([])
            
        try:
            # Cargar solo el segmento necesario
            seg = AudioSegment.from_file(self.audio_path)[start_ms:end_ms]
            mono = seg.set_channels(1)
            
            # Convertir a numpy array
            arr = np.array(mono.get_array_of_samples()).astype(np.float32)
            max_val = float(1 << (8 * mono.sample_width - 1))
            arr = arr / max_val
            
            # Calcular envelope con la resolución especificada
            if len(arr) == 0:
                return np.array([]), np.array([])
                
            if len(arr) <= resolution:
                # Si el segmento es más pequeño que la resolución, devolver todos los puntos
                return arr, arr
            
            # Calcular el tamaño de cada bucket
            bucket_size = len(arr) // resolution
            if bucket_size < 1:
                bucket_size = 1
                
            # Ajustar la longitud para que sea divisible por bucket_size
            trimmed_len = len(arr) - (len(arr) % bucket_size)
            trimmed = arr[:trimmed_len]
            
            # Reshape y calcular min/max
            reshaped = trimmed.reshape(-1, bucket_size)
            mins = reshaped.min(axis=1)
            maxs = reshaped.max(axis=1)
            
            return mins, maxs
        except Exception as e:
            print(f"Error al obtener segmento de waveform: {e}")
            return np.array([]), np.array([])

    def play(self):
        if not self.is_ready:
            print("El medio no está listo para reproducir")
            return
            
        print("Iniciando reproducción...")
        result = self.player.play()
        
        if result == -1:
            print("Error al iniciar reproducción")
        else:
            print("Reproducción iniciada")

    def pause(self):
        self.player.pause()
        print("Reproducción pausada")

    def stop(self):
        self.player.stop()
        print("Reproducción detenida")

    def is_playing(self) -> bool:
        return bool(self.player.is_playing())

    def position_ms(self) -> int:
        try:
            t = self.player.get_time()
            return int(t) if t is not None else 0
        except Exception:
            return 0

    def set_position_ms(self, ms: int):
        if self.duration_ms > 0:
            self.player.set_time(int(max(0, min(ms, self.duration_ms - 1))))
            print(f"Posición establecida en: {ms} ms")

    def set_speed(self, speed: float):
        speed = max(0.25, min(speed, 4.0))
        result = self.player.set_rate(speed)
        print(f"Velocidad cambiada a: {speed}x (resultado: {result})")

    def set_pitch(self, semitones: float):
        pass  # No implementado en esta versión

    def set_volume(self, vol: int):
        vol = max(0, min(100, vol))
        self.player.audio_set_volume(vol)
        print(f"Volumen establecido en: {vol}%")

# Widget para visualización de forma de onda optimizado
class WaveformWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.audio_processor: Optional[AudioProcessor] = None
        self.duration_ms = 0
        self.line_height = 64
        self.line_spacing = 12
        self.playhead_ms = 0
        self.zoom_level = 1.0
        self.visible_lines = 0
        self.total_lines = 0
        self.time_per_line = 0
        self.line_cache: Dict[int, Tuple[np.ndarray, np.ndarray]] = {}
        self.line_time_info: Dict[int, Dict[str, str]] = {}
        
        # Temporizador para actualizar el playhead
        self._timer = QTimer(self)
        self._timer.setInterval(100)
        self._timer.timeout.connect(self._update_playhead)
        
        # Proveedor de posición actual
        self._position_provider = None

    def set_audio_processor(self, processor: AudioProcessor):
        self.audio_processor = processor
        self._calculate_layout()
        self.update()

    def set_position_provider(self, provider):
        self._position_provider = provider
        self._timer.start()

    def _update_playhead(self):
        if self._position_provider:
            self.playhead_ms = self._position_provider()
            self.update()

    def _calculate_layout(self):
        if not self.audio_processor or self.audio_processor.duration_ms <= 0:
            return
            
        self.duration_ms = self.audio_processor.duration_ms
        
        # Calcular cuántas líneas necesitamos
        # Cada línea representa aproximadamente 30 segundos a zoom normal
        base_time_per_line = 30000  # 30 segundos en ms
        self.time_per_line = int(base_time_per_line / self.zoom_level)
        
        # Asegurar que cada línea tenga al menos 5 segundos
        self.time_per_line = max(5000, self.time_per_line)
        
        # Calcular el número total de líneas
        self.total_lines = int(np.ceil(self.duration_ms / self.time_per_line))
        
        # Calcular cuántas líneas son visibles
        self.visible_lines = int(np.ceil(self.height() / (self.line_height + self.line_spacing))) + 2
        
        # Limpiar caché
        self.line_cache.clear()
        self.line_time_info.clear()
        
        # Precalcular información de tiempo para cada línea
        for i in range(self.total_lines):
            start_ms = i * self.time_per_line
            end_ms = min((i + 1) * self.time_per_line, self.duration_ms)
            self.line_time_info[i] = {
                'start': fmt_ms(start_ms),
                'end': fmt_ms(end_ms),
                'start_ms': start_ms,
                'end_ms': end_ms
            }
        
        # Establecer tamaño mínimo del widget
        min_height = self.total_lines * (self.line_height + self.line_spacing)
        self.setMinimumHeight(min_height)

    def zoom_in(self):
        self.zoom_level = min(10.0, self.zoom_level * 1.5)
        self._calculate_layout()
        self.update()

    def zoom_out(self):
        self.zoom_level = max(0.1, self.zoom_level / 1.5)
        self._calculate_layout()
        self.update()

    def _get_visible_line_range(self):
        """Determinar qué líneas son visibles actualmente"""
        scroll_area = self.parent()
        if not isinstance(scroll_area, QScrollArea):
            return 0, self.total_lines - 1
            
        scroll_y = scroll_area.verticalScrollBar().value()
        viewport_height = scroll_area.viewport().height()
        
        first_line = max(0, scroll_y // (self.line_height + self.line_spacing))
        last_line = min(
            self.total_lines - 1,
            (scroll_y + viewport_height) // (self.line_height + self.line_spacing) + 1
        )
        
        return first_line, last_line

    def _load_line_data(self, line_idx: int):
        """Cargar datos para una línea específica si no están en caché"""
        if line_idx in self.line_cache:
            return
            
        if line_idx not in self.line_time_info:
            return
            
        time_info = self.line_time_info[line_idx]
        start_ms = time_info['start_ms']
        end_ms = time_info['end_ms']
        
        # Calcular resolución basada en el ancho disponible
        width = max(1, self.width() - 100)  # Dejar espacio para el tiempo
        resolution = max(100, width // 2)  # Al menos 100 puntos, máximo la mitad del ancho
        
        # Obtener datos de forma de onda para esta línea
        mins, maxs = self.audio_processor.get_waveform_segment(start_ms, end_ms, resolution)
        self.line_cache[line_idx] = (mins, maxs)

    def paintEvent(self, event):
        super().paintEvent(event)
        if not self.audio_processor or self.duration_ms <= 0:
            return
            
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        
        # Configurar fuentes y colores
        painter.setFont(self.font())
        pen_time = QPen(Qt.GlobalColor.black)
        pen_axis = QPen(Qt.GlobalColor.gray)
        pen_wave = QPen(Qt.GlobalColor.darkCyan)
        pen_playhead = QPen(Qt.GlobalColor.red)
        
        # Determinar qué líneas son visibles
        first_line, last_line = self._get_visible_line_range()
        
        # Dibujar solo las líneas visibles
        for line_idx in range(first_line, last_line + 1):
            if line_idx >= self.total_lines:
                break
                
            # Cargar datos para esta línea si no están en caché
            self._load_line_data(line_idx)
            
            # Obtener información de tiempo para esta línea
            time_info = self.line_time_info.get(line_idx, {})
            start_time = time_info.get('start', '00:00')
            end_time = time_info.get('end', '00:00')
            
            # Calcular posición Y de esta línea
            y = line_idx * (self.line_height + self.line_spacing)
            mid_y = y + self.line_height // 2
            
            # Dibujar tiempo de la línea
            painter.setPen(pen_time)
            painter.drawText(5, mid_y - 10, start_time)
            painter.drawText(5, mid_y + 20, end_time)
            
            # Dibujar eje central
            painter.setPen(pen_axis)
            axis_x = 100  # Posición X del eje
            axis_width = max(1, self.width() - axis_x - 10)
            painter.drawLine(axis_x, mid_y, axis_x + axis_width, mid_y)
            
            # Obtener datos de forma de onda para esta línea
            if line_idx in self.line_cache:
                mins, maxs = self.line_cache[line_idx]
                if len(mins) > 0 and len(maxs) > 0:
                    # Dibujar forma de onda usando QPainterPath para mejor rendimiento
                    painter.setPen(pen_wave)
                    
                    path_min = QPainterPath()
                    path_max = QPainterPath()
                    
                    # Calcular el factor de escala para ajustar al ancho disponible
                    x_scale = axis_width / max(1, len(mins))
                    
                    for i in range(len(mins)):
                        x = axis_x + int(i * x_scale)
                        y_min = mid_y - int(mins[i] * (self.line_height // 2 - 2))
                        y_max = mid_y - int(maxs[i] * (self.line_height // 2 - 2))
                        
                        if i == 0:
                            path_min.moveTo(x, y_min)
                            path_max.moveTo(x, y_max)
                        else:
                            path_min.lineTo(x, y_min)
                            path_max.lineTo(x, y_max)
                    
                    painter.drawPath(path_min)
                    painter.drawPath(path_max)
            
            # Dibujar playhead si está en esta línea
            if line_idx in self.line_time_info:
                line_start_ms = self.line_time_info[line_idx]['start_ms']
                line_end_ms = self.line_time_info[line_idx]['end_ms']
                
                if line_start_ms <= self.playhead_ms <= line_end_ms:
                    # Calcular posición X del playhead dentro de esta línea
                    line_duration = line_end_ms - line_start_ms
                    if line_duration > 0:
                        position_in_line = (self.playhead_ms - line_start_ms) / line_duration
                        playhead_x = axis_x + int(position_in_line * axis_width)
                        
                        painter.setPen(pen_playhead)
                        painter.drawLine(playhead_x, y, playhead_x, y + self.line_height)

# Ventana principal de la aplicación
class AudioPlayer(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Audinux - Reproductor de Audio")
        self.resize(1200, 700)

        # Inicializar componentes primero
        self.audio = AudioProcessor()
        self.markers = MarkersManager()
        self.playlist = Playlist()
        self.settings = AppSettings()
        
        # Inicializar variables de estado antes de construir la UI
        self.current_rate = self.settings.last_rate()
        self.current_volume = 70  # Volumen inicial
        
        # Ahora construir la UI
        self._build_ui()
        self._connect_signals()

        # Configurar temporizador
        self.timer = QTimer(self)
        self.timer.setInterval(200)  # Reducir frecuencia de actualización
        self.timer.timeout.connect(self._on_tick)
        self.timer.start()
        
        # Aplicar configuración inicial
        self._apply_rate()
        self._apply_volume()

    def _build_ui(self):
        central = QWidget()
        root = QVBoxLayout(central)
        self.setCentralWidget(central)

        # Barra de herramientas
        tb = QHBoxLayout()
        self.btn_open = QPushButton("Abrir… (Ctrl+O)")
        self.btn_play = QPushButton("▶ Play/Pause (Espacio)")
        self.btn_stop = QPushButton("■ Stop (S)")
        tb.addWidget(self.btn_open)
        tb.addWidget(self.btn_play)
        tb.addWidget(self.btn_stop)
        tb.addStretch(1)

        # Controles de velocidad
        self.lbl_rate = QLabel("Velocidad: 1.00x")
        self.sld_rate = QSlider(Qt.Orientation.Horizontal)
        self.sld_rate.setRange(25, 400)
        self.sld_rate.setValue(int(self.current_rate * 100))
        self.sld_rate.setSingleStep(5)
        tb.addWidget(self.lbl_rate)
        tb.addWidget(self.sld_rate)
        
        # Controles de volumen
        self.lbl_volume = QLabel("Volumen: 70")
        self.sld_volume = QSlider(Qt.Orientation.Horizontal)
        self.sld_volume.setRange(0, 100)
        self.sld_volume.setValue(self.current_volume)
        self.sld_volume.setSingleStep(5)
        tb.addWidget(self.lbl_volume)
        tb.addWidget(self.sld_volume)

        root.addLayout(tb)

        # Área principal con waveform y panel lateral
        splitter = QSplitter()
        root.addWidget(splitter, 1)

        # Panel izquierdo - Waveform
        left = QWidget()
        left_layout = QVBoxLayout(left)

        zoom_bar = QHBoxLayout()
        self.btn_zoom_in = QPushButton("Zoom +")
        self.btn_zoom_out = QPushButton("Zoom −")
        zoom_bar.addWidget(self.btn_zoom_in)
        zoom_bar.addWidget(self.btn_zoom_out)
        zoom_bar.addStretch(1)
        left_layout.addLayout(zoom_bar)

        self.wave = WaveformWidget()
        self.wave.set_audio_processor(self.audio)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(self.wave)
        left_layout.addWidget(scroll, 1)

        time_bar = QHBoxLayout()
        self.lbl_time = QLabel("00:00:00 / 00:00:00")
        time_bar.addWidget(self.lbl_time)
        time_bar.addStretch(1)
        left_layout.addLayout(time_bar)

        splitter.addWidget(left)

        # Panel derecho - Listas y marcadores
        right = QWidget()
        rlayout = QVBoxLayout(right)

        rlayout.addWidget(QLabel("Lista de reproducción"))
        self.lst_playlist = QListWidget()
        rlayout.addWidget(self.lst_playlist, 1)
        btns_pl = QHBoxLayout()
        self.btn_add_pl = QPushButton("Añadir (Ctrl+P)")
        self.btn_next = QPushButton("Siguiente ▶▶")
        self.btn_prev = QPushButton("◀◀ Anterior")
        btns_pl.addWidget(self.btn_add_pl)
        btns_pl.addWidget(self.btn_prev)
        btns_pl.addWidget(self.btn_next)
        rlayout.addLayout(btns_pl)

        rlayout.addWidget(QLabel("Marcadores"))
        self.lst_markers = QListWidget()
        rlayout.addWidget(self.lst_markers, 1)
        mk_bar = QHBoxLayout()
        self.ed_marker = QLineEdit()
        self.ed_marker.setPlaceholderText("Nombre del marcador…")
        self.btn_add_marker = QPushButton("Añadir (M)")
        self.btn_loop = QPushButton("Loop A↔B (L)")
        mk_bar.addWidget(self.ed_marker)
        mk_bar.addWidget(self.btn_add_marker)
        mk_bar.addWidget(self.btn_loop)
        rlayout.addLayout(mk_bar)

        splitter.addWidget(right)
        splitter.setSizes([900, 300])

    def _connect_signals(self):
        self.btn_open.clicked.connect(self._open_file)
        self.btn_play.clicked.connect(self._toggle_play)
        self.btn_stop.clicked.connect(self._stop)
        self.btn_zoom_in.clicked.connect(self.wave.zoom_in)
        self.btn_zoom_out.clicked.connect(self.wave.zoom_out)
        self.sld_rate.valueChanged.connect(self._on_rate_changed)
        self.sld_volume.valueChanged.connect(self._on_volume_changed)
        self.btn_add_pl.clicked.connect(self._add_to_playlist)
        self.btn_next.clicked.connect(self._next_track)
        self.btn_prev.clicked.connect(self._prev_track)
        self.btn_add_marker.clicked.connect(self._add_marker)
        self.lst_markers.itemDoubleClicked.connect(self._jump_to_marker)
        self.btn_loop.clicked.connect(self._toggle_loop)
        self.wave.set_position_provider(self._current_ms)

    def _open_file(self):
        start_dir = self.settings.last_dir() or os.path.expanduser('~')
        path, _ = QFileDialog.getOpenFileName(
            self, "Abrir audio", start_dir,
            "Audio (*.mp3 *.wav *.flac *.ogg)"
        )
        if not path:
            return
        self.settings.set_last_dir(os.path.dirname(path))
        self._load_path(path, add_to_playlist=True)

    def _load_path(self, path: str, add_to_playlist: bool = False):
        try:
            self.audio.load_audio(path)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"No se pudo cargar el archivo:\n{e}")
            return
        if add_to_playlist:
            self.playlist.add(path)
            self._refresh_playlist()
        self.markers.load_for(path)
        self._refresh_markers()
        
        # Configurar el widget de waveform
        self.wave.set_audio_processor(self.audio)
        
        self.audio.set_position_ms(0)
        self._apply_rate()
        self._apply_volume()
        self._update_time_label()
        self.setWindowTitle(f"Audinux — {os.path.basename(path)}")

    def _toggle_play(self):
        if self.audio.is_playing():
            self.audio.pause()
        else:
            self.audio.play()

    def _stop(self):
        self.audio.stop()

    def _on_rate_changed(self, value: int):
        self.current_rate = round(value / 100.0, 2)
        self._apply_rate()

    def _apply_rate(self):
        self.audio.set_speed(self.current_rate)
        self.lbl_rate.setText(f"Velocidad: {self.current_rate:.2f}x")
        self.settings.set_last_rate(self.current_rate)

    def _on_volume_changed(self, value: int):
        self.current_volume = value
        self._apply_volume()

    def _apply_volume(self):
        self.audio.set_volume(self.current_volume)
        self.lbl_volume.setText(f"Volumen: {self.current_volume}")

    def _add_to_playlist(self):
        start_dir = self.settings.last_dir() or os.path.expanduser('~')
        paths, _ = QFileDialog.getOpenFileNames(
            self, "Añadir a la lista", start_dir,
            "Audio (*.mp3 *.wav *.flac *.ogg)"
        )
        for p in paths:
            self.playlist.add(p)
        self._refresh_playlist()

    def _next_track(self):
        nxt = self.playlist.next()
        if nxt:
            self._load_path(nxt)

    def _prev_track(self):
        prv = self.playlist.prev()
        if prv:
            self._load_path(prv)

    def _refresh_playlist(self):
        self.lst_playlist.clear()
        for p in self.playlist.all():
            item = QListWidgetItem(os.path.basename(p))
            item.setToolTip(p)
            self.lst_playlist.addItem(item)

    def _add_marker(self):
        name = self.ed_marker.text().strip() or "Marcador"
        ms = self._current_ms()
        self.markers.add_marker(ms, name)
        self._refresh_markers(select_last=True)
        self.ed_marker.clear()

    def _refresh_markers(self, select_last=False):
        self.lst_markers.clear()
        for m in self.markers.list():
            item = QListWidgetItem(f"{m.name} — {fmt_ms(m.ms)}")
            item.setData(Qt.ItemDataRole.UserRole, m.ms)
            self.lst_markers.addItem(item)
        if select_last and self.lst_markers.count() > 0:
            self.lst_markers.setCurrentRow(self.lst_markers.count() - 1)

    def _jump_to_marker(self, item):
        ms = int(item.data(Qt.ItemDataRole.UserRole))
        self.audio.set_position_ms(ms)

    def _toggle_loop(self):
        items = self.lst_markers.selectedItems()
        if len(items) >= 2:
            ms1 = int(items[0].data(Qt.ItemDataRole.UserRole))
            ms2 = int(items[1].data(Qt.ItemDataRole.UserRole))
            if ms1 == ms2:
                QMessageBox.warning(self, "Loop", "Selecciona dos marcadores diferentes.")
                return
            start, end = (ms1, ms2) if ms1 < ms2 else (ms2, ms1)
            self.markers.set_loop(start, end)
            self.btn_loop.setText("Loop A↔B: ON (L)")
        else:
            self.markers.set_loop(None, None)
            self.btn_loop.setText("Loop A↔B (L)")

    def _on_tick(self):
        jump_to = self.markers.should_loop(self._current_ms())
        if jump_to is not None:
            self.audio.set_position_ms(jump_to)
        self._update_time_label()

    def _update_time_label(self):
        cur = self._current_ms()
        tot = self.audio.duration_ms
        self.lbl_time.setText(f"{fmt_ms(cur)} / {fmt_ms(tot)}")

    def _current_ms(self) -> int:
        return self.audio.position_ms()

    def keyPressEvent(self, e):
        key = e.key()
        mod = e.modifiers()
        
        if key == Qt.Key.Key_Space:
            self._toggle_play()
            e.accept()
            return
        if key == Qt.Key.Key_S:
            self._stop()
            e.accept()
            return
        if key in (Qt.Key.Key_Plus, Qt.Key.Key_Equal, Qt.Key.Key_Z):
            self.wave.zoom_in()
            e.accept()
            return
        if key in (Qt.Key.Key_Minus, Qt.Key.Key_Underscore, Qt.Key.Key_X):
            self.wave.zoom_out()
            e.accept()
            return
        if key == Qt.Key.Key_M:
            self._add_marker()
            e.accept()
            return
        if key == Qt.Key.Key_L:
            self._toggle_loop()
            e.accept()
            return
        if key == Qt.Key.Key_Period:
            nxt = self._next_marker_after(self._current_ms())
            if nxt: self.audio.set_position_ms(nxt.ms)
            e.accept()
            return
        if key == Qt.Key.Key_Comma:
            prv = self._prev_marker_before(self._current_ms())
            if prv: self.audio.set_position_ms(prv.ms)
            e.accept()
            return
        if key in (Qt.Key.Key_Left, Qt.Key.Key_Right):
            delta = 5000
            if mod & Qt.KeyboardModifier.ControlModifier:
                delta = 30000
            elif mod & Qt.KeyboardModifier.ShiftModifier:
                delta = 1000
            if key == Qt.Key.Key_Left:
                self.audio.set_position_ms(max(0, self._current_ms() - delta))
            else:
                self.audio.set_position_ms(self._current_ms() + delta)
            e.accept()
            return
        if key == Qt.Key.Key_O and (mod & Qt.KeyboardModifier.ControlModifier):
            self._open_file()
            e.accept()
            return
        if key == Qt.Key.Key_P and (mod & Qt.KeyboardModifier.ControlModifier):
            self._add_to_playlist()
            e.accept()
            return
        if key == Qt.Key.Key_Up and (mod & Qt.KeyboardModifier.ControlModifier):
            self._nudge_rate(+0.05)
            e.accept()
            return
        if key == Qt.Key.Key_Down and (mod & Qt.KeyboardModifier.ControlModifier):
            self._nudge_rate(-0.05)
            e.accept()
            return
        super().keyPressEvent(e)

    def _nudge_rate(self, delta: float):
        v = int(round((self.current_rate + delta) * 100))
        v = max(25, min(400, v))
        self.sld_rate.setValue(v)

    def _next_marker_after(self, ms: int) -> Optional[Marker]:
        return self.markers.nearest_after(ms)

    def _prev_marker_before(self, ms: int) -> Optional[Marker]:
        return self.markers.nearest_before(ms)

# Función principal
def main():
    app = QApplication(sys.argv)
    player = AudioPlayer()
    player.show()
    sys.exit(app.exec())

if __name__ == '__main__':
    main()
