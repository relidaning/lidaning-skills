"""Portable runtime settings; environment > selected TOML > shipped defaults."""
import os
from pathlib import Path
import tomllib

DEFAULT_FILE = Path(__file__).resolve().parents[1] / "config.toml"


def load_config(path=None, environ=None):
    env = os.environ if environ is None else environ
    selected = path or env.get("RAG_CONFIG_FILE")
    source = Path(selected).expanduser().resolve() if selected else DEFAULT_FILE
    with DEFAULT_FILE.open("rb") as stream:
        defaults = tomllib.load(stream)["runtime"]
    values = dict(defaults)
    if selected:
        with source.open("rb") as stream:
            override = tomllib.load(stream)
        unknown_sections = set(override) - {"runtime"}
        if unknown_sections:
            raise ValueError(f"Unknown configuration sections: {sorted(unknown_sections)}")
        override = override.get("runtime", {})
        unknown = set(override) - set(defaults)
        if unknown:
            raise ValueError(f"Unknown runtime settings: {sorted(unknown)}")
        values.update(override)
    for key, default in defaults.items():
        raw = env.get(key, values[key])
        # Compose forwards these existing shell overrides as empty when unset.
        if key in ("LLM_MODEL", "LLM_BASE_URL") and raw == "":
            raw = values[key]
        try:
            if isinstance(default, int):
                if isinstance(raw, bool) or isinstance(raw, float):
                    raise ValueError()
                values[key] = int(raw)
            elif isinstance(default, float):
                values[key] = float(raw)
            else:
                if not isinstance(raw, str):
                    raise ValueError()
                values[key] = raw
        except (ValueError, TypeError):
            raise ValueError(f"Invalid {key}: expected {type(default).__name__}") from None
        value = values[key]
        if isinstance(default, (int, float)):
            import math
            if not math.isfinite(value) or value <= 0:
                raise ValueError(f"Invalid {key}: must be positive and finite")
        elif key != "LLM_BASE_URL" and not value.strip():
            raise ValueError(f"Invalid {key}: must not be empty")
    for key in ("RAG_PORT", "CHROMA_PORT"):
        if values[key] > 65535:
            raise ValueError(f"Invalid {key}: must be <= 65535")
    if values["CHUNK_TOKENS"] > values["EMBED_MAX_TOKENS"]:
        raise ValueError("CHUNK_TOKENS must be <= EMBED_MAX_TOKENS")
    for key in ("RAG_LOG_DIR", "EMBED_MODEL_DIR"):
        value = Path(values[key]).expanduser()
        values[key] = str(value if value.is_absolute() else source.parent / value)
    return values


CONFIG = load_config()
