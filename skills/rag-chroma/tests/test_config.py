"""Offline configuration contracts; no server, model or vault needed."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1] / "rag-mcp"
if not (ROOT / "rag_config.py").exists():
    ROOT = Path("/app")
sys.path.insert(0, str(ROOT))
from rag_config import load_config


class ConfigTests(unittest.TestCase):
    def test_defaults_preserve_deployed_settings(self):
        settings = load_config(environ={})
        self.assertEqual(settings["CHROMA_PORT"], 8000)
        self.assertEqual(settings["EMBED_THREADS"], 8)
        self.assertEqual(settings["CHUNK_TOKENS"], 300)
        self.assertEqual(settings["LLM_MODEL"], "gpt-4o-mini")
        self.assertNotIn("LLM_API_KEY", settings)

    def test_partial_file_environment_precedence_and_relative_paths(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "custom.toml"
            path.write_text('[runtime]\nRAG_PORT=9000\nRAG_LOG_DIR="audit"\nLLM_MODEL="custom"\n')
            settings = load_config(environ={"RAG_CONFIG_FILE": str(path), "RAG_PORT": "9100", "LLM_MODEL": ""})
            self.assertEqual(settings["RAG_PORT"], 9100)
            self.assertEqual(settings["LLM_MODEL"], "custom")
            self.assertEqual(settings["RAG_LOG_DIR"], str(Path(directory) / "audit"))
            self.assertEqual(settings["CHROMA_HOST"], "localhost")

    def test_invalid_settings_fail_with_name(self):
        for key, value in (("WATCH_INTERVAL", "0"), ("RAG_PORT", "65536"),
                           ("EMBED_BATCH", "-1"), ("VAULT_MCP_TIMEOUT", "nan"),
                           ("EMBED_THREADS", "many"), ("CHUNK_TOKENS", "513"),
                           ("VAULT_MCP_URL", "")):
            with self.subTest(key=key), self.assertRaisesRegex(ValueError, key):
                load_config(environ={key: value})

    def test_unknown_settings_and_invalid_toml_fail(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "custom.toml"
            path.write_text('[runtime]\nTYPO_PORT=8082\n')
            with self.assertRaisesRegex(ValueError, "TYPO_PORT"):
                load_config(path, environ={})
            path.write_text('[runtime]\nRAG_PORT=true\n')
            with self.assertRaisesRegex(ValueError, "RAG_PORT"):
                load_config(path, environ={})
            path.write_text('[broken')
            with self.assertRaises(ValueError):
                load_config(path, environ={})

    def test_client_loads_configuration_outside_project_directory(self):
        client = ROOT.parent / "scripts" / "rag_mcp.py"
        if not client.exists():
            client = Path("/client/rag_mcp.py")
        with tempfile.TemporaryDirectory() as directory:
            env = {key: value for key, value in os.environ.items()
                   if key not in load_config(environ={}) and key != "RAG_CONFIG_FILE"}
            env["RAG_MCP_URL"] = "http://example.invalid:9100"
            result = subprocess.run([sys.executable, "-c",
                "import runpy; c=runpy.run_path(" + repr(str(client)) + "); print(c['BASE'])"],
                cwd=directory, env=env, text=True, capture_output=True, check=True)
            self.assertEqual(result.stdout.strip(), "http://example.invalid:9100")
