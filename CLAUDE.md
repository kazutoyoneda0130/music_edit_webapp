# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

FastAPI + React web app version of `../music_edit_app` (the PySide6 desktop app): upload multiple songs, detect BPM/beats, reorder/skip blocks per song, configure crossfade junctions between songs, preview, and export a combined mix. Google OAuth-gated (allowlisted emails only — see `ALLOWED_EMAILS`). Deployed to Fly.io; see `HOSTING.md` for hosting decisions, cost breakdown, and production incidents (OOM, sample-rate/accuracy tradeoff, CPU sizing) worth reading before touching `music_engine/` or storage/rate-limit config.

## Commands

Backend dev server:
```
uvicorn app.main:app --reload --app-dir backend
```

Frontend dev server (separate origin, proxied via CORS in dev):
```
cd frontend && npm run dev
npm run build   # tsc -b && vite build — output consumed by backend/app/main.py's SPA static mount
npm run lint    # oxlint
```

Tests (run from repo root — `pytest.ini` sets `asyncio_mode = auto`):
```
PYTHONPATH=/Users/kazuto/Applications/my_company/music_edit_webapp asdf exec python3 -m pytest tests/ -q
PYTHONPATH=/Users/kazuto/Applications/my_company/music_edit_webapp asdf exec python3 -m pytest tests/test_coordinator.py -v   # single file
```
Test deps: `pip install -r tests/requirements-dev.txt` (pulls in `music_engine/requirements.txt` and `backend/requirements.txt` too).

Docker (matches production):
```
docker compose up --build
```

Python pinned to 3.11.4 via `.tool-versions` (asdf). `ffmpeg` must be on PATH.

## Architecture

Three top-level Python packages, in dependency order:

- **`music_engine/`** — UI-independent core, ported from `music_edit_app/`. `analyze_bpm.py` and `concat_audio.py` are near-identical to their desktop counterparts (see `tests/test_audio_engine_parity.py`, which guards against the two diverging). `audio_engine.py` is new here: it's the pure-function rewrite of logic that lived inline in the desktop app's `MainWindow`/`SongPanel` (junction eights→seconds conversion, timeline building, `resolve_junction_specs`/`resolve_junctions`, `build_combined_timeline`, `build_multi_combined_audio`). Read the module docstring in `audio_engine.py` — it documents an intentional quirk (junction BPM/crossfade settings are keyed by fixed slot position, not by which songs actually end up adjacent after reordering) inherited on purpose from the desktop version.

- **`backend/app/`** — FastAPI app, routers under `auth/`, `songs/`, `combine/`:
  - `auth/` — Google OAuth login/callback (`authlib`), session cookie (`SessionMiddleware`), email allowlist check (`settings.allowed_emails_set`). `deps.get_current_user` gates `songs` and `combine` routers.
  - `songs/routes.py` — upload, BPM/block analysis (via `music_engine.analyze_bpm`), single-song block rebuild. Enforces both file-size (`MAX_UPLOAD_BYTES`) and post-analysis duration (`MAX_DURATION_SECONDS`) caps — size alone isn't sufficient because heavily-compressed low-bitrate files can smuggle long audio past a size limit.
  - `combine/routes.py` + `combine/coordinator.py` — timeline/preview/export. `LatestWinsCoordinator` (`coordinator.py`) is the key concurrency primitive: if a user changes params while a preview/export is still building, it does **not** cancel or ignore the new request — it lets the in-flight build finish, then reruns with the latest params, and every caller gets a result via its own dedicated `Future` (a shared-variable approach was tried and produced a confirmed race condition where a caller could receive another round's result). This is the HTTP port of the desktop app's `CombinedPreviewWorker` + queued-preview pattern.
  - `storage.py` — upload/preview/export file paths under `settings.storage_dir`, per-directory TTL sweep (`sweep_expired`, invoked hourly from `main.py`'s startup task), and a global `STORAGE_CAP_BYTES` (3GB) as a backstop against TTL sweep not keeping up.
  - `ratelimit.py` — in-memory only, single-process assumption (`SlidingWindowLimiter`) except `DailyByteQuotaLimiter`-style state that's persisted to the storage volume because it caps real Fly.io egress cost and must survive process restarts/deploys.
  - `main.py` — mounts `frontend/dist` as static files and serves `index.html` for any non-`/api` path (SPA fallback) when a build exists; in dev (no `dist/`), nothing is mounted and Vite serves the frontend separately.

- **`frontend/src/`** — React 19 + TypeScript + Zustand, Vite build, `@dnd-kit` for drag-reordering blocks, oxlint for linting. State split into `store/{authStore,songsStore,junctionsStore,playbackStore}.ts`; API calls centralized in `api/client.ts`/`api/types.ts`. Components map roughly 1:1 to backend concerns: `SongPanel`/`BlockList(Item)` (per-song block editing), `JunctionControls` (crossfade config between songs), `TransportBar` (preview playback), `AuthGate`/`LoginPage` (Google OAuth flow).

## Design system

`frontend/src/index.css` uses kazuto's workspace-wide "stylish café" design tokens (warm cream bg, espresso-brown text, rust/terracotta accent, `Shippori Mincho` + `Zen Kaku Gothic New`) — same values as `homepage/` and documented in the `design-system-standard` memory. Applied 2026-07-19 by remapping this app's existing CSS-variable token set (`--bg`, `--accent`, `--danger`, `--highlight`, etc. in `index.css`) to the new palette; no component (`.tsx`) file needed changes since none had hardcoded colors or inline styles — everything already flowed through the CSS variables. `--serif`/Shippori Mincho is used only for the two "brand moment" headings (`.app-header h1`, `.login-page h1`), not the smaller functional headings (song panel titles, junction control labels), which stay in the sans font for readability at small sizes. When restyling `music_edit_app` (the desktop counterpart) to match, translate these same token values into Qt Style Sheets rather than inventing new colors.

## Keep in sync with music_edit_app

`music_engine/analyze_bpm.py` and `music_engine/concat_audio.py` should stay behaviorally identical to `music_edit_app/analyze_bpm.py` and `music_edit_app/concat_audio.py` — `tests/test_audio_engine_parity.py` exists specifically to catch drift. If you fix a bug or tune behavior in one, port it to the other and re-run that test.
