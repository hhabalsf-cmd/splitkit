"""The LayerLab seed payload must pass the same validation the API applies."""

import importlib.util
from pathlib import Path

from splitkit.api.schemas import ExperimentCreate

_PATH = Path(__file__).resolve().parents[2] / "scripts" / "seed_layerlab.py"
_spec = importlib.util.spec_from_file_location("seed_layerlab", _PATH)
seed = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(seed)


def test_payload_is_a_valid_experiment():
    body = ExperimentCreate.model_validate(seed.build_payload())
    assert body.key == "home-suggestions-position"
    assert [v.name for v in body.variants] == ["control", "treatment"]


def test_refuses_to_run_without_url_and_key(monkeypatch):
    monkeypatch.delenv("SPLITKIT_URL", raising=False)
    monkeypatch.delenv("SPLITKIT_ADMIN_KEY", raising=False)
    assert seed.main([]) == 2
