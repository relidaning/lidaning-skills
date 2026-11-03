"""Manage skill-owned Codex MCP blocks without rewriting other TOML settings.

Requires Python 3.11+. Existing manually configured server names are preserved;
resolve name collisions explicitly instead of overwriting user configuration.
"""
import json
import re
import sys
from pathlib import Path

try:
    import tomllib
except ImportError:
    raise SystemExit("Codex MCP installation requires Python 3.11 or newer")


def convert(entry):
    if "command" in entry:
        out = {k: entry[k] for k in ("command", "args", "cwd") if k in entry}
        env, inherited = {}, []
        for key, value in entry.get("env", {}).items():
            if value == "${" + key + "}":
                inherited.append(key)
            elif "${" in value:
                raise ValueError(f"Unsupported environment substitution for {key}")
            else:
                env[key] = value
        if env:
            out["env"] = env
        if inherited:
            out["env_vars"] = inherited
        return out
    if entry.get("type") == "sse":
        raise ValueError("Codex requires Streamable HTTP, not legacy SSE")
    if "${" in entry["url"]:
        raise ValueError("Codex MCP URLs must be literal URLs")
    out = {"url": entry["url"]}
    static, dynamic = {}, {}
    for key, value in entry.get("headers", {}).items():
        match = re.fullmatch(r"\$\{(\w+)\}", value)
        bearer = re.fullmatch(r"Bearer \$\{(\w+)\}", value)
        if key.lower() == "authorization" and bearer:
            out["bearer_token_env_var"] = bearer[1]
        elif match:
            dynamic[key] = match[1]
        elif "${" in value:
            raise ValueError(f"Unsupported header substitution for {key}")
        else:
            static[key] = value
    if static:
        out["http_headers"] = static
    if dynamic:
        out["env_http_headers"] = dynamic
    return out


def toml_value(value):
    if isinstance(value, dict):
        return "{ " + ", ".join(f"{json.dumps(k)} = {toml_value(v)}" for k, v in value.items()) + " }"
    return json.dumps(value, ensure_ascii=False)


def update(action, config, manifest):
    text = config.read_text() if config.exists() else ""
    original = text
    tomllib.loads(text)  # Fail before writing if the user's config is invalid.
    for name, entry in json.loads(manifest.read_text()).items():
        if not re.fullmatch(r"[\w-]+", name):
            raise ValueError(f"Unsupported MCP server name: {name}")
        begin = f"# BEGIN lidaning-skills MCP {name}\n"
        end = f"# END lidaning-skills MCP {name}\n"
        pattern = re.compile(r"^" + re.escape(begin) + r".*?^" + re.escape(end), re.M | re.S)
        text = pattern.sub("", text)
        if action == "add":
            if name in tomllib.loads(text).get("mcp_servers", {}):
                raise ValueError(f"MCP server {name!r} already exists outside installer-managed blocks in {config}")
            values = convert(entry)
            block = begin + f"[mcp_servers.{json.dumps(name)}]\n"
            block += "".join(f"{key} = {toml_value(value)}\n" for key, value in values.items())
            text = text.rstrip("\n") + "\n\n" + block + end
    tomllib.loads(text)  # Check the complete merged document before writing.
    if text != original:
        config.parent.mkdir(parents=True, exist_ok=True)
        config.write_text(text)


if __name__ == "__main__":
    action, config, manifest = sys.argv[1:]
    if action not in ("add", "remove"):
        raise SystemExit(f"Unknown action: {action}")
    try:
        update(action, Path(config), Path(manifest))
    except (ValueError, KeyError) as error:
        raise SystemExit(str(error))
