# Spectrobuster Architecture (Phase 1)

## Entry points

- `main.py`: preferred launcher.
- `full app.py`: temporary compatibility wrapper (legacy command still works).

## Source layout

- `src/spectrobuster/app.py`: current GUI application (main window + orchestration).
- `src/spectrobuster/argyll.py`: Argyll executable resolution and environment/path setup.
- `src/spectrobuster/domain/colorimetry.py`: pure color conversion helpers.

## Tooling layout

- `tools/env_checks/check_mpl_path_bases.py`
- `tools/env_checks/check_mpl_path_slots.py`
- `tools/env_checks/check_colour_cri_api.py`
- `tools/env_checks/check_mpl_deepcopy.py`

## Current data and binaries

- Runtime measurement data remains in `mesures/` (unchanged in phase 1).
- Bundled Argyll binaries remain in `mac/Argyll_V3.5.0/bin` and `windows/Argyll_V3.5-2.0/bin`.
- `src/spectrobuster/argyll.py` now tries local bundled binaries first, then falls back to `spotread` in PATH.

## Next planned split

- Extract spectrum parsing logic from `app.py` to `services/spectrum_parser.py`.
- Extract measurement persistence/history to `services/measurement_store.py`.
- Move platform paths and settings into dedicated infra modules.
