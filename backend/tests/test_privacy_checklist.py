"""Static checks for the scope boundary in docs/PRIVACY.md. Behavioural checks (EXIF stripping, TTL, delete, auth,
rate limits, audit log) live in test_sanitize / test_lifecycle / test_security."""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

from app.adapters import vlm_clues
from app.config import BACKEND_DIR, REPO_ROOT

FORBIDDEN_IMPORTS = ("face_recognition", "dlib", "deepface", "insightface", "facenet", "mediapipe", "cv2", "retinaface")


def _python_sources() -> list[Path]:
    return [p for p in (BACKEND_DIR / "app").rglob("*.py")] + [p for p in (BACKEND_DIR / "scripts").rglob("*.py")]


def test_no_face_detection_or_recognition_libraries_are_imported():
    pattern = re.compile(r"^\s*(?:import|from)\s+(" + "|".join(FORBIDDEN_IMPORTS) + r")\b", re.M)
    offenders = [str(p) for p in _python_sources() if pattern.search(p.read_text())]
    assert offenders == []


def test_declared_dependencies_contain_no_face_libraries():
    text = (BACKEND_DIR / "pyproject.toml").read_text().lower()
    assert not [lib for lib in FORBIDDEN_IMPORTS if lib in text]


def test_vlm_prompt_tells_the_model_to_ignore_people_and_abstain():
    assert "IGNORE PEOPLE" in vlm_clues.SYSTEM_PROMPT and "abstain" in vlm_clues.SYSTEM_PROMPT.lower()


def test_env_example_holds_no_secret_values():
    for line in (REPO_ROOT / ".env.example").read_text().splitlines():
        match = re.match(r"^#?\s*(OPERA_API_KEY|OPENAI_API_KEY|VITE_OPERA_API_KEY|OPERA_DB_PASSWORD)\s*=\s*(\S.*)$", line)
        if match:
            assert match.group(2).startswith("#"), f"{match.group(1)} has a value in .env.example"


def test_uploads_weights_databases_and_downloaded_images_are_git_ignored():
    probes = [
        "backend/uploads/x.jpg",
        "backend/.model_cache/w.bin",
        "backend/data/opera.sqlite",
        "backend/fixtures/benchmark/opera-commons-v1/images/a.jpg",
        ".env",
    ]
    result = subprocess.run(["git", "check-ignore", *probes], cwd=REPO_ROOT, capture_output=True, text=True)
    assert set(result.stdout.split()) == set(probes), result.stdout


def test_no_api_key_shaped_strings_in_tracked_backend_files():
    tracked = subprocess.run(
        ["git", "ls-files", "backend", ".env.example"], cwd=REPO_ROOT, capture_output=True, text=True
    ).stdout.split()
    pattern = re.compile(r"sk-[A-Za-z0-9_-]{20,}")
    for name in tracked:
        path = REPO_ROOT / name
        if path.suffix in {".png", ".jpg", ".jpeg", ".sqlite"} or not path.is_file():
            continue
        assert not pattern.search(path.read_text(errors="ignore")), name
