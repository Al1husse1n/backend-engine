from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_backend_has_no_voxide_coupling():
    hits = []
    for path in (ROOT / "app").rglob("*.py"):
        text = path.read_text(encoding="utf-8").lower()
        if "voxide" in text:
            hits.append(str(path.relative_to(ROOT)))
    assert hits == []


def test_requirements_have_no_voxide_dependency():
    requirements = (ROOT / "requirements.txt").read_text(encoding="utf-8").lower()
    assert "voxide" not in requirements
