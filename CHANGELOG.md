# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Versions are calendar-based: `YYYY.MM.DD`, with an extra `.N` if we ship
more than once on the same day.

## [Unreleased]


## [2026.09.04] - 2026-09-04

### Changed

- README documents requirements, removal, and a root `preview.png` for the marketplace
- Release script no longer fetches remote git before running checks

## [2026.08.17.1] - 2026-08-17

### Changed

- Bar hover no longer shows the raw stats tooltip; click opens the panel

### Changed

- Panel meters, hero, and chips follow theme accent / muted / urgent colors
- Tasteful fade and meter animations on the dropdown

## [2026.08.17] - 2026-08-17

### Added

- Native Omarchy bar widget for CPU, memory, GPU, disk, and temperatures
- Detail panel with meters, top processes, and cached disk directories
- NVIDIA (`nvidia-smi`) and AMD (sysfs) GPU support
- In-panel settings accordion (pills for metrics, look, click, disk, poll, alerts)
- `barStyle` Icons / Text so the bar can show `CPU` `MEM` `GPU` instead of glyphs
- Hover tooltips and one-line hints on every settings group

### Changed

- Settings stay collapsed so the dropdown is stats-first

### Fixed

- Fake CPU spikes from two monitors sampling `/proc/stat` a few milliseconds apart

[Unreleased]: https://github.com/thehamsti/omarchy-vitals/compare/v2026.09.04...HEAD
[2026.09.04]: https://github.com/thehamsti/omarchy-vitals/releases/tag/v2026.09.04
[2026.08.17.1]: https://github.com/thehamsti/omarchy-vitals/releases/tag/v2026.08.17.1
[2026.08.17]: https://github.com/thehamsti/omarchy-vitals/releases/tag/v2026.08.17
