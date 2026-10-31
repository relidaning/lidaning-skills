"""Scheduler checks using fake CLI replies and isolated state; no live services."""
import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

SKILL = Path(__file__).resolve().parents[1] / "skills/claude-maxer"


def load(name):
    spec = importlib.util.spec_from_file_location(name, SKILL / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


backend = load("codex_backend")


def quotas(now=1000):
    return {"rateLimitsByLimitId": {"codex": {
        "primary": {"usedPercent": 40, "windowDurationMins": 300, "resetsAt": now + 3000},
        "secondary": {"usedPercent": 20, "windowDurationMins": 10080, "resetsAt": now + 604800},
    }}}


def output(*events, rc=0):
    return subprocess.CompletedProcess([], rc, "\n".join(map(json.dumps, events)), "")


class BackendTests(unittest.TestCase):
    def test_windows_selected_by_duration_and_bucket(self):
        result = quotas()
        bucket = result["rateLimitsByLimitId"]["codex"]
        bucket["primary"], bucket["secondary"] = bucket["secondary"], bucket["primary"]
        result["rateLimitsByLimitId"]["another"] = {}
        usage = backend.normalize_usage(result, 1000)
        self.assertEqual((usage["five_pct"], usage["seven_pct"]), (40, 20))
        with self.assertRaises(backend.CodexError):
            backend.normalize_usage(result, 1000, "missing")

    def test_legacy_single_bucket_and_idle_window(self):
        bucket = quotas()["rateLimitsByLimitId"]["codex"]
        bucket["primary"].update(usedPercent=0, resetsAt=None)
        usage = backend.normalize_usage({"rateLimits": bucket}, 1000)
        self.assertIsNone(usage["five_reset"])
        bucket["limitId"] = "different"
        with self.assertRaises(backend.CodexError):
            backend.normalize_usage({"rateLimits": bucket}, 1000)

    def test_bad_missing_expired_quotas_fail_closed(self):
        for key, value in (("usedPercent", None), ("usedPercent", float("nan")),
                           ("usedPercent", -1), ("usedPercent", True),
                           ("usedPercent", 101), ("resetsAt", 999),
                           ("resetsAt", None), ("windowDurationMins", 15)):
            with self.subTest(key=key, value=value):
                result = quotas()
                result["rateLimitsByLimitId"]["codex"]["primary"][key] = value
                with self.assertRaises(backend.CodexError):
                    backend.normalize_usage(result, 1000)
        with self.assertRaises(backend.CodexError):
            backend.normalize_usage({}, 1000)

    def test_handshake_and_quota_read_only(self):
        proc = Mock()
        proc.stdin = io.StringIO()
        proc.stdout = io.StringIO(json.dumps({"id": 1, "result": {}}) + "\n" +
                                  json.dumps({"method": "notice"}) + "\n" +
                                  json.dumps({"id": 2, "result": quotas()}) + "\n")
        sent = []
        proc.stdin.close = lambda: sent.extend(proc.stdin.getvalue().splitlines())
        with patch.object(backend.subprocess, "Popen", return_value=proc):
            self.assertEqual(backend.read_rate_limits(), quotas())
        self.assertEqual([json.loads(line)["method"] for line in sent],
                         ["initialize", "initialized", "account/rateLimits/read"])
        proc.terminate.assert_called_once()

    def test_auth_error_and_timeout_cleanup(self):
        for lines in ('{"id":1,"error":{"message":"secret"}}\n', None):
            proc = Mock()
            proc.stdin = io.StringIO()
            proc.stdout = io.StringIO(lines or "")
            with patch.object(backend.subprocess, "Popen", return_value=proc):
                with self.assertRaises(backend.CodexError) as raised:
                    backend.read_rate_limits(timeout=0 if lines is None else 1)
            self.assertNotIn("secret", str(raised.exception))
            proc.terminate.assert_called_once()

    def test_jsonl_reply_and_tokens(self):
        result = backend.parse_output(output(
            {"type": "thread.started"},
            {"type": "item.completed", "item": {"type": "agent_message", "text": "RESULT: done"}},
            {"type": "turn.completed", "usage": {
                "input_tokens": 100, "cached_input_tokens": 30, "output_tokens": 5}}))
        self.assertEqual(result["result"], "RESULT: done")
        self.assertEqual(result["modelUsage"]["codex"]["inputTokens"], 70)
        self.assertEqual(result["modelUsage"]["codex"]["cacheReadInputTokens"], 30)
        self.assertNotIn("total_cost_usd", result)

    def test_failed_incomplete_and_invalid_workers(self):
        for process in (output({"type": "turn.failed"}), output({"type": "turn.completed"}),
                        output({"type": "error"}, rc=1),
                        subprocess.CompletedProcess([], 0, "not json", "")):
            with self.assertRaises(ValueError):
                backend.parse_output(process)

    def test_news_disables_configured_mcp_plugins_and_shell(self):
        with tempfile.TemporaryDirectory() as home, patch.dict(os.environ, HOME=home, CODEX_HOME=home):
            Path(home, "config.toml").write_text('[mcp_servers.vault]\nurl="http://unused"\n'
                                                 '[plugins."some@plugin"]\nenabled=true\n')
            cmd = backend.worker_command("News", "test-model", news=True)
        self.assertIn('mcp_servers."vault".enabled=false', cmd)
        self.assertIn('plugins."some@plugin".enabled=false', cmd)
        self.assertIn("shell_tool", cmd)
        self.assertIn("read-only", cmd)
        self.assertNotIn("--add-dir", cmd)
        self.assertEqual(cmd[cmd.index("--model") + 1], "test-model")


class SchedulerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.env = patch.dict(os.environ, HOME=self.tmp.name, CODEX_HOME=self.tmp.name + "/codex")
        self.env.start()
        self.addCleanup(self.env.stop)
        self.m = load("maxer")
        self.modules = patch.dict(sys.modules, codex_backend=backend)
        self.modules.start()
        self.addCleanup(self.modules.stop)
        self.m.select_agent("codex")
        # Lock files must also be isolated from the running scheduler.
        self.m.TICK_LOCK = self.tmp.name + "/tick.lock"
        self.m.RUN_LOCK = self.tmp.name + "/run.lock"
        self.usage = backend.normalize_usage(quotas(), 1000)

    def test_independent_quota_state_shared_legacy_queue_state(self):
        self.assertTrue(self.m.BUDGET_PATH.startswith(self.tmp.name + "/codex/"))
        self.assertTrue(self.m.PAUSE_PATH.startswith(self.tmp.name + "/codex/"))
        self.assertIn("/.claude/state/", self.m.VAULT_FAILS_PATH)
        self.assertIn("/.claude/state/", self.m.ROTATION_PATH)
        self.assertIn("/.claude/state/", self.m.WORK_DIR)

    def test_model_mapping_and_claude_default(self):
        cmd = self.m.worker_command("task", "claude-opus-5-5")
        self.assertEqual(cmd[:2], ["codex", "exec"])
        self.assertNotIn("claude-opus-5-5", cmd)
        self.assertNotIn("--max-budget-usd", cmd)
        self.m.CFG["codex_model"] = "chosen-codex-model"
        self.assertIn("chosen-codex-model", self.m.worker_command("task"))
        original = load("maxer")
        self.assertEqual(original.AGENT, "claude")
        self.assertEqual(original.worker_command("task")[:2], ["claude", "-p"])

    def test_refresh_and_failure_does_not_reuse_snapshot(self):
        with patch.object(backend, "read_rate_limits", return_value=quotas()), \
                patch.object(backend.time, "time", return_value=1000):
            self.assertEqual(self.m.fresh_usage()["five_pct"], 40)
        with patch.object(backend, "read_rate_limits", side_effect=backend.CodexError("offline")):
            with self.assertRaises(backend.CodexError):
                self.m.fresh_usage()

    def test_tick_live_refresh_dispatch_dedup_and_pause(self):
        with patch.object(self.m.time, "time", return_value=1000), \
                patch.object(self.m, "fresh_usage", return_value=self.usage) as refresh, \
                patch.object(self.m, "cmd_run", return_value=0) as run:
            self.m.cmd_tick()
            self.m.cmd_tick()
            self.assertEqual(refresh.call_count, 2)
            run.assert_called_once_with(False)
            Path(self.m.PAUSE_PATH).write_text('{"since":1000}')
            self.m.cmd_tick()
            self.assertEqual(refresh.call_count, 2)

    def test_tick_failure_never_opens_or_runs(self):
        with patch.object(self.m, "fresh_usage", side_effect=backend.CodexError("offline")), \
                patch.object(self.m, "cmd_run") as run, patch.object(self.m, "cmd_open") as opener:
            with self.assertRaises(backend.CodexError):
                self.m.cmd_tick()
            run.assert_not_called()
            opener.assert_not_called()

    def test_idle_tick_opens_once_in_pin_hour(self):
        idle = dict(self.usage, five_pct=0, five_reset=None)
        with patch.object(self.m, "fresh_usage", return_value=idle), \
                patch.object(self.m, "pin_slot", return_value=500), \
                patch.object(self.m, "cmd_open", return_value=0) as opener:
            self.m.cmd_tick()
            self.m.cmd_tick()
            opener.assert_called_once_with(False)

    def test_weekly_target_and_reset_margin(self):
        self.assertTrue(self.m.gate(self.usage, 1000)[0])
        self.assertFalse(self.m.gate(dict(self.usage, five_pct=95), 1000)[0])
        self.assertFalse(self.m.gate(dict(self.usage, seven_pct=95), 1000)[0])
        self.assertFalse(self.m.gate(dict(self.usage, five_reset=1100), 1000)[0])

    def test_worker_timeout_kills_process_group(self):
        proc = Mock(pid=123)
        proc.communicate.side_effect = [subprocess.TimeoutExpired("fake", 1), ("", "")]
        with patch.object(self.m.subprocess, "Popen", return_value=proc), \
                patch.object(self.m.os, "killpg") as kill:
            with self.assertRaises(subprocess.TimeoutExpired):
                self.m.execute_worker(["fake"], self.tmp.name, 1)
        kill.assert_called_once_with(123, self.m.signal.SIGKILL)

    def test_all_worker_kinds_accept_codex_jsonl(self):
        def reply(text):
            return output({"type": "item.completed", "item": {"type": "agent_message", "text": text}},
                          {"type": "turn.completed", "usage": {"input_tokens": 10}})

        # All external effects are mocked; no vault, GitHub or real git call.
        with patch.object(self.m, "execute_worker") as execute, \
                patch.object(self.m, "vault_append") as append, \
                patch.object(self.m, "covered_titles", return_value=[]), \
                patch.object(self.m, "queue_call", return_value=(0, "")), \
                patch.object(self.m.subprocess, "run"), \
                patch.object(self.m, "pr_state", return_value="MERGED"):
            execute.return_value = reply("APP: skip no work\nPR: none")
            result = self.m.run_optimize_task({"app": "test", "path": self.tmp.name,
                                               "prompt": "Optimize"}, 10**12)
            self.assertNotIn("error", result)
            self.assertEqual(execute.call_args.args[0][:2], ["codex", "exec"])

            execute.return_value = reply("REVIEW: done")
            result = self.m.run_review_task({"app": "test", "path": self.tmp.name,
                                             "prompt": "Review", "prs": [
                                                 {"url": "https://example.invalid/1", "number": 1}]}, 10**12)
            self.assertNotIn("error", result)

            repo = Path(self.tmp.name, "repo")
            (repo / ".git").mkdir(parents=True)
            self.m.VAULT_TASK_ROOT = self.tmp.name
            execute.return_value = reply(f"REPO: {repo}\nRESULT: done")
            with patch.object(self.m, "last_commit_ts", return_value=("master", 10**12)):
                self.assertNotIn("error", self.m.run_vault_task("Implement", 10**12))

            execute.return_value = reply("1. **[Example](https://example.invalid)** — An update.")
            result = self.m.run_task("news", "News", "Find news", "2026-10-31", 10**12)
            self.assertNotIn("error", result)
            self.assertEqual(result["items"], 1)
            self.assertIn("read-only", execute.call_args.args[0])
            self.assertTrue(append.called)


class CronTests(unittest.TestCase):
    def test_cron_blocks_are_provider_specific_and_default_stays_claude(self):
        script = str(SKILL / "enroll_cron.sh")
        default = subprocess.run([script, "print"], capture_output=True, text=True, check=True).stdout
        codex = subprocess.run([script, "print", "--agent", "codex"],
                               capture_output=True, text=True, check=True).stdout
        self.assertIn("# BEGIN claude-maxer schedule", default)
        self.assertNotIn("--agent", default)
        self.assertIn("# BEGIN codex-maxer schedule", codex)
        self.assertIn("--agent codex tick >> /tmp/codex-maxer-cron.log", codex)
        invalid = subprocess.run([script, "print", "--agent", "wrong"], capture_output=True)
        self.assertEqual(invalid.returncode, 2)


if __name__ == "__main__":
    unittest.main()
