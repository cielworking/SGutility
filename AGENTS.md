# SG Alerts (`sgalerts.com`) — Project Rules & Architecture

## Core Workflow Rules
- **Git commits:** Always commit with `git -c user.name="Ciel" -c user.email="cielworkmail@gmail.com"`.
- **Rebase before push:** GitHub Actions updates `data/*.json` every 15–60 minutes, so always run `git pull --rebase -X theirs origin main` before `git push origin main`.
- **Required tests before pushing:**
  - `python -m unittest discover -s tests -q`
  - `node tests/test-air-quality.cjs`
  - `node --check <file.js>` for modified JS files.
- **Asset version bumps (`tests/test_theme.py`):** Every non-underscore `.html` file (including `offline.html`) must contain `class="theme-control"`, `sga-theme-mode`, `theme.js?v=3`, and `style.css?v=41` (update all `.html` files + `scripts/render-weather-pages.py` + `tests/test_theme.py` in lockstep whenever bumping versions).
- **Cloudflare cache:** After pushing frontend/data changes, purge Zone `1bb5911d961ce01303ee58d5bb88b76e` once GitHub Pages finishes deploying (~20–30s).

## Infrastructure Map
- **Cloudflare Account:** `8a499f71ea6bbf2d2e4c746e8165aa2a` · **Zone (`sgalerts.com`):** `1bb5911d961ce01303ee58d5bb88b76e`
- **Workers:**
  - `sgalerts-ai` (`workers/sgalerts-ai.js`) → `sgalerts.com/api/checkpoint-ai*` (serves GitHub Actions `YOLOX-M` + Smart Zoom results if ≤ 22 mins old; DETR fallback).
  - `sgalerts-lane-reports` (`workers/sgalerts-lane-reports.js`) → `sgalerts.com/api/lane-reports*` (KV `SGALERTS_LANE_REPORTS` `7edac44ef65a47c58f0e9de79ca2f6f9`; anonymous daily FC/NFC lane votes, auto-expires 00:00 SGT, 10m hashed-IP cooldown).
  - `sgalerts-reactions` (`workers/sgalerts-reactions.js`) → `sgalerts.com/api/reactions*` (KV `SGALERTS_REACTIONS`).

## Checkpoint AI Vision (`scripts/analyze-checkpoints.py`)
- Uses Apache-2.0 **`YOLOX-M` ONNX** + **Adaptive 2-Pass Smart Zoom** (`CAMERA_TILES` + 2×2 super-zoom on dense tiles) and supports **`YOLO26` NMS-free E2E `(1, N, 6)`** and **`YOLO11` `(1, 4+C, N)`** custom ONNX models via `.cache/models/sgalerts_custom.onnx`.
- **Keep `CAMERA_ZONES` synced** between `scripts/analyze-checkpoints.py` and `workers/sgalerts-ai.js`:
  - `2701` Causeway central barrier: `(535, 1069) → (1920, 362)` (upper-left = `towards_jb`, lower-right beside water pipes = `towards_sg`).
  - `2702` Approach/BKE: right `CAUSEWAY` ramp + elevated bike flyover = `towards_jb` (+ 24/7 relative headlight-peak bike estimator); left `BKE` = `towards_sg`.
  - `4703` Tuas Second Link: weekday AM + Sunday PM contraflow schedule + night visual headlight-vs-taillight auto-contraflow detector (`detect_4703_contraflow`).
  - `4713` Tuas Outbound: right `JOHOR` viaduct + bottom horizontal bike lane = `towards_jb`.
- **Colab Distillation:** `notebooks/sgalerts_checkpoint_distill_colab.ipynb` trains `YOLO26s` in Google Colab, saves `sgalerts_custom.onnx` to Google Drive (`sgalerts_distill/`), and auto-shuts down GPU via `runtime.unassign()`.
