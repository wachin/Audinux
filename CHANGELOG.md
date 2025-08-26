# Changelog

All notable changes to **Audinux** will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),  
and this project adheres to [Semantic Versioning](https://semver.org/).

---

## [Unreleased]

### Added
- **Waveform caching**: The audio waveform is now precomputed once and cached in memory, greatly improving performance for very long audio files (several hours).
- **Click-to-seek support**: Users can click anywhere on the waveform to jump playback to that position, similar to WhatsApp voice notes.

### Changed
- Updated waveform drawing logic to use cached data instead of decoding audio segments on the fly.
- Reduced CPU usage and improved UI responsiveness when scrolling or zooming.

### Fixed
- Player no longer depends on having the standalone VLC application open.

