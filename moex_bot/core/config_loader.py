import yaml
from pathlib import Path

_config_cache = None

def load_config(path: str = None):
    global _config_cache
    if _config_cache is None:
        cfg_path = Path(path or Path(__file__).resolve().parents[1] / "config.yaml")
        with open(cfg_path, "r", encoding="utf-8") as f:
            _config_cache = yaml.safe_load(f)
    return _config_cache
