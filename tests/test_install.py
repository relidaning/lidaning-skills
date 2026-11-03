"""Installer integration tests. All destinations are isolated temporary paths."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import tomllib
import unittest

REPO = Path(__file__).resolve().parents[1]


class InstallTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="skills install ")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.project = self.root / "project"
        self.home = self.root / "home"
        self.project.mkdir()
        self.home.mkdir()
        self.env = dict(os.environ, HOME=str(self.home),
                        CODEX_HOME=str(self.home / "custom-codex"),
                        XDG_CONFIG_HOME=str(self.home / "config"), LDN_AGENT="claude")

    def run_cli(self, args, ok=True, entry="install.sh", env=None):
        command = [str(REPO / entry), *args]
        if entry == "cli.js":
            command.insert(0, "node")
        result = subprocess.run(command, cwd=self.project, env=env or self.env,
                                capture_output=True, text=True)
        if ok:
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        else:
            self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        return result.stdout + result.stderr

    def read_config(self, path=None):
        return tomllib.loads((path or self.project / ".codex/config.toml").read_text())

    def test_codex_complete_package_reinstall_remove(self):
        args = ["learning-instruct", "--project", "--codex"]
        target = self.project / ".agents/skills/learning-instruct"
        for _ in range(2):
            self.run_cli(args)
            self.assertTrue(target.is_symlink())
            self.assertEqual(target.resolve(), REPO / "skills/learning-instruct")
            self.assertTrue((target / "besmart_sync.py").is_file())
        self.assertFalse((self.project / ".claude").exists())
        self.run_cli([*args, "--remove"])
        self.assertFalse(target.is_symlink())
        self.assertTrue((REPO / "skills/learning-instruct/SKILL.md").is_file())

    def test_default_claude_and_both_and_all(self):
        self.run_cli(["english-practice", "--project"])
        self.assertTrue((self.project / ".claude/skills/english-practice").is_symlink())
        self.assertFalse((self.project / ".agents").exists())
        self.run_cli(["english-practice", "--project", "--agent", "both"])
        self.assertTrue((self.project / ".agents/skills/english-practice").is_symlink())
        self.assertFalse((self.project / ".opencode").exists())
        self.run_cli(["english-practice", "--project", "--agent=all"])
        self.assertTrue((self.project / ".opencode/skills/english-practice").is_symlink())
        self.run_cli(["english-practice", "--project", "--agent=all", "--remove"])
        for root in (".claude", ".agents", ".opencode"):
            self.assertFalse((self.project / root / "skills/english-practice").is_symlink())

    def test_global_paths_and_env_agent(self):
        env = dict(self.env, LDN_AGENT="codex")
        self.run_cli(["nextcloud", "--global"], env=env)
        self.assertTrue((self.home / ".agents/skills/nextcloud").is_symlink())
        config = self.home / "custom-codex/config.toml"
        server = self.read_config(config)["mcp_servers"]["nextcloud"]
        self.assertEqual(server["command"], "uvx")
        self.assertEqual(set(server["env_vars"]),
                         {"NEXTCLOUD_HOST", "NEXTCLOUD_USERNAME", "NEXTCLOUD_PASSWORD"})
        self.assertNotIn("env", server)
        self.assertFalse((self.project / ".codex").exists())
        self.run_cli(["nextcloud", "--global", "--remove"], env=env)
        self.assertNotIn("mcp_servers", self.read_config(config))

    def test_mcp_preserves_settings_and_comments(self):
        config = self.project / ".codex/config.toml"
        config.parent.mkdir()
        original = '# keep this comment\nmodel = "chosen-model"\n[mcp_servers.other]\nurl = "http://example.test/mcp"\n'
        config.write_text(original)
        args = ["rag-chroma", "--project", "--agent", "codex", "--mcp-only"]
        self.run_cli(args)
        first = config.read_text()
        self.run_cli(args)
        self.assertEqual(config.read_text(), first)
        self.assertTrue(first.startswith(original))
        self.assertEqual(self.read_config()["mcp_servers"]["rag"]["url"], "http://localhost:8081/mcp")
        self.assertFalse((self.project / ".agents").exists())
        self.run_cli(["rag-chroma", "--project", "--codex", "--remove"])
        self.assertEqual(self.read_config()["model"], "chosen-model")
        self.assertEqual(set(self.read_config()["mcp_servers"]), {"other"})
        self.assertIn("# keep this comment", config.read_text())

    def test_mcp_collision_and_invalid_toml_preserved(self):
        config = self.project / ".codex/config.toml"
        config.parent.mkdir()
        for original in ('[mcp_servers.rag]\nurl = "http://custom.test/mcp"\n', 'invalid = ['):
            config.write_text(original)
            self.run_cli(["rag-chroma", "--project", "--codex", "--mcp-only"], ok=False)
            self.assertEqual(config.read_text(), original)

    def test_legacy_install_migration_and_local_file_protection(self):
        target = self.project / ".claude/skills/english-practice"
        target.mkdir(parents=True)
        (target / "SKILL.md").symlink_to(REPO / "skills/english-practice/SKILL.md")
        (target / "deleted.md").symlink_to(REPO / "skills/english-practice/deleted.md")
        self.run_cli(["english-practice", "--project"])
        self.assertTrue(target.is_symlink())
        target.unlink()
        target.mkdir()
        local = target / "notes.md"
        local.write_text("user content")
        self.run_cli(["english-practice", "--project"], ok=False)
        self.assertEqual(local.read_text(), "user content")

    def test_broken_directory_link_repaired_and_removed(self):
        target = self.project / ".agents/skills/english-practice"
        target.parent.mkdir(parents=True)
        target.symlink_to(self.root / "missing")
        self.run_cli(["english-practice", "--project", "--codex"])
        self.assertTrue((target / "SKILL.md").is_file())
        target.unlink()
        target.symlink_to(self.root / "missing-again")
        self.run_cli(["english-practice", "--project", "--codex", "--remove"])
        self.assertFalse(target.is_symlink())

    def test_ldn_codex_list_and_mcp_injection(self):
        self.run_cli(["english-practice", "--project", "--codex"])
        output = self.run_cli(["list", "--agent", "codex"], entry="bin/ldn")
        line = next(line for line in output.splitlines() if "english-practice" in line)
        self.assertIn("[installed]", line)
        self.run_cli(["mcp", "inject", "--agent", "codex"], entry="bin/ldn")
        self.assertEqual(set(self.read_config()["mcp_servers"]), {"nextcloud", "obsidian-vault", "rag"})
        self.assertFalse((self.project / ".mcp.json").exists())

    def test_ldn_global_interactive_install_list_and_remove(self):
        # Stub only the checkbox UI; exercise the real installer and preselection.
        tools = self.root / "bin"
        tools.mkdir()
        gum = tools / "gum"
        gum.write_text("#!/usr/bin/env python3\n"
                       "import json, os, sys\n"
                       "from pathlib import Path\n"
                       "sys.stdin.read()\n"
                       "Path(os.environ['GUM_ARGS']).write_text(json.dumps(sys.argv[1:]))\n"
                       "print(os.environ['GUM_CHOICE'])\n")
        gum.chmod(0o755)
        env = dict(self.env, PATH=str(tools) + os.pathsep + self.env["PATH"],
                   GUM_ARGS=str(self.root / "gum-args.json"), GUM_CHOICE="english-practice")
        roots = {"claude": self.home / ".claude/skills",
                 "codex": self.home / ".agents/skills",
                 "opencode": self.home / "config/opencode/skills"}
        for agent in ("claude", "codex", "opencode", "both", "all"):
            with self.subTest(agent=agent):
                args = ["--global", "--agent", agent]
                self.run_cli(args, entry="bin/ldn", env=env)
                expected = ("claude", "codex") if agent == "both" else tuple(roots) if agent == "all" else (agent,)
                for name, root in roots.items():
                    self.assertEqual((root / "english-practice").is_symlink(), name in expected)
                output = self.run_cli(["list", *args], entry="bin/ldn", env=env)
                line = next(line for line in output.splitlines() if "english-practice" in line)
                self.assertIn("[installed]", line)
                project_output = self.run_cli(["list", "--project", "--agent", agent], entry="bin/ldn", env=env)
                line = next(line for line in project_output.splitlines() if "english-practice" in line)
                self.assertIn("[not installed]", line)
                self.run_cli(args, entry="bin/ldn", env=dict(env, GUM_CHOICE=""))
                gum_args = json.loads((self.root / "gum-args.json").read_text())
                self.assertIn("--selected=english-practice", gum_args)
                for root in roots.values():
                    self.assertFalse((root / "english-practice").is_symlink())
                self.assertEqual(list(self.project.iterdir()), [])

    def test_ldn_global_codex_mcp_injection(self):
        self.run_cli(["mcp", "--global", "inject", "--agent", "codex"], entry="bin/ldn")
        config = self.home / "custom-codex/config.toml"
        self.assertEqual(set(self.read_config(config)["mcp_servers"]),
                         {"nextcloud", "obsidian-vault", "rag"})
        self.assertEqual(list(self.project.iterdir()), [])

    def test_node_cli_uses_shared_installer(self):
        args = ["add", "obsidian-local", "--project", "--agent=codex"]
        self.run_cli(args, entry="cli.js")
        self.assertTrue((self.project / ".agents/skills/obsidian-local/scripts/vault-mcp.sh").is_file())
        self.assertIn("obsidian-vault", self.read_config()["mcp_servers"])
        self.run_cli(["rm", "obsidian-local", "--project", "--codex"], entry="cli.js")
        self.assertFalse((self.project / ".agents/skills/obsidian-local").is_symlink())

    def test_invalid_agent_rejected(self):
        self.run_cli(["english-practice", "--agent", "unknown"], ok=False)
        self.assertEqual(list(self.project.iterdir()), [])

    def test_open_code_mcp_unchanged(self):
        self.run_cli(["rag-chroma", "--project", "--opencode"])
        config = json.loads((self.project / "opencode.json").read_text())
        self.assertEqual(config["mcp"]["servers"]["rag"],
                         {"type": "remote", "url": "http://localhost:8081/mcp"})
        self.run_cli(["rag-chroma", "--project", "--opencode", "--remove"])
        self.assertNotIn("mcp", json.loads((self.project / "opencode.json").read_text()))


if __name__ == "__main__":
    unittest.main()
