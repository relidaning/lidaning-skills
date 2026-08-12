#!/usr/bin/env python3
"""
Bridge between the learning-instruct skill and the besmart app's study-plan API.

besmart (/data/apps/besmart) owns the canonical list of curricula (study_plans)
and their steps (plan_tasks) -- this script lets learning-instruct read that
list to seed a learning track, and write progress back as the user masters
each part, so besmart's dashboard/streak stay in sync with what actually
happened in the tutoring conversation.

No secret is stored in this repo: the JWT signing secret is read at call time
from the running besmart container (or its docker-compose.yml as a fallback),
never hardcoded here.

Plan tasks are a WBS tree, not a flat list: each task has an optional
parent_task_id and a sort_order among its siblings. A task with children has
no completion state of its own -- completion is derived client-side from
whether every leaf descendant is done -- so only set --completed on leaves.

Usage:
  besmart_sync.py list [--all]                          # incomplete plans by default
  besmart_sync.py plan <plan_id>
  besmart_sync.py tree <plan_id>                         # plan's tasks rendered as an indented tree
  besmart_sync.py create-plan <name> <description> <start_date> <end_date>
  besmart_sync.py update-plan <plan_id> [--name] [--description] [--start-date] [--end-date] [--completed|--incomplete]
  besmart_sync.py create-task <plan_id> <name> <description> <planned_start> <planned_end> [--parent-task-id <id>]
  besmart_sync.py update-task <plan_id> <task_id> [--name] [--description] [--planned-start] [--planned-end] [--completed|--incomplete]
  besmart_sync.py complete-task <plan_id> <task_id>
  besmart_sync.py complete-plan <plan_id>
  besmart_sync.py delete-task <plan_id> <task_id>        # cascades to all descendants
  besmart_sync.py delete-plan <plan_id>
  besmart_sync.py indent-task <plan_id> <task_id>        # becomes last child of its previous sibling
  besmart_sync.py outdent-task <plan_id> <task_id>       # becomes a sibling right after its old parent
  besmart_sync.py move-task <plan_id> <task_id> <up|down>  # reorder among siblings

update-plan/update-task only send the fields you pass, so omitted fields keep
their current value server-side. All commands print JSON to stdout (except
`tree`, which prints a human-readable outline). Dates are 'YYYY-MM-DD'.
"""
import argparse
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request

BASE_URL = os.environ.get("BESMART_URL", "http://127.0.0.1:5090")
USER_ID = int(os.environ.get("BESMART_USER_ID", "2"))
USER_EMAIL = os.environ.get("BESMART_EMAIL", "453882101@qq.com")
CONTAINER = os.environ.get("BESMART_CONTAINER", "besmart-besmart-1")
COMPOSE_FILE = os.environ.get("BESMART_COMPOSE", "/data/apps/besmart/docker-compose.yml")


def _get_secret() -> str:
    env = os.environ.get("BESMART_JWT_SECRET")
    if env:
        return env
    try:
        out = subprocess.run(
            ["docker", "exec", CONTAINER, "printenv", "JWT_SECRET"],
            capture_output=True, text=True, timeout=5,
        )
        if out.returncode == 0 and out.stdout.strip():
            return out.stdout.strip()
    except (OSError, subprocess.SubprocessError):
        pass
    try:
        with open(COMPOSE_FILE) as f:
            for line in f:
                line = line.strip()
                if "JWT_SECRET=" in line:
                    return line.split("JWT_SECRET=", 1)[1].strip("'\" ")
    except OSError:
        pass
    raise RuntimeError(
        "Could not determine besmart JWT_SECRET (checked $BESMART_JWT_SECRET, "
        f"`docker exec {CONTAINER} printenv`, and {COMPOSE_FILE})"
    )


def _token() -> str:
    import jwt  # PyJWT
    return jwt.encode(
        {"id": USER_ID, "email": USER_EMAIL, "display_name": None},
        _get_secret(),
        algorithm="HS256",
    )


def _request(method: str, path: str, body=None):
    url = f"{BASE_URL.rstrip('/')}{path}"
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Authorization", f"Bearer {_token()}")
    if data is not None:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"{method} {path} -> {e.code}: {e.read().decode()}")


def cmd_list(args):
    plans = _request("GET", "/api/plans")["data"]
    if not args.all:
        plans = [p for p in plans if not p["is_completed"]]
    print(json.dumps(plans, indent=2, ensure_ascii=False))


def cmd_plan(args):
    print(json.dumps(_request("GET", f"/api/plans/{args.plan_id}")["data"], indent=2, ensure_ascii=False))


def _build_tree(tasks):
    by_parent = {}
    for t in tasks:
        by_parent.setdefault(t["parent_task_id"], []).append(t)
    for siblings in by_parent.values():
        siblings.sort(key=lambda t: t["sort_order"])

    def attach(parent_id):
        return [dict(t, children=attach(t["id"])) for t in by_parent.get(parent_id, [])]

    return attach(None)


def _leaf_stats(node):
    if not node["children"]:
        return (1, 1 if node["is_completed"] else 0)
    total = done = 0
    for c in node["children"]:
        t, d = _leaf_stats(c)
        total += t
        done += d
    return total, done


def _print_tree(nodes, depth=0):
    for n in nodes:
        total, done = _leaf_stats(n)
        mark = "x" if done == total else " "
        progress = "" if not n["children"] else f" ({done}/{total})"
        print(f"{'  ' * depth}[{mark}] #{n['id']} {n['name']}{progress}")
        if n.get("description"):
            for line in n["description"].splitlines():
                print(f"{'  ' * depth}      {line}")
        _print_tree(n["children"], depth + 1)


def cmd_tree(args):
    plan = _request("GET", f"/api/plans/{args.plan_id}")["data"]
    print(f"{plan['name']} ({plan['start_date']} -> {plan['end_date']})")
    _print_tree(_build_tree(plan["tasks"]))


def cmd_create_plan(args):
    body = {"name": args.name, "description": args.description, "start_date": args.start_date, "end_date": args.end_date}
    print(json.dumps(_request("POST", "/api/plans", body)["data"], indent=2, ensure_ascii=False))


def cmd_update_plan(args):
    body = {}
    if args.name is not None:
        body["name"] = args.name
    if args.description is not None:
        body["description"] = args.description
    if args.start_date is not None:
        body["start_date"] = args.start_date
    if args.end_date is not None:
        body["end_date"] = args.end_date
    if args.completed is not None:
        body["is_completed"] = args.completed
    print(json.dumps(_request("PUT", f"/api/plans/{args.plan_id}", body)["data"], indent=2, ensure_ascii=False))


def cmd_create_task(args):
    body = {"name": args.name, "description": args.description, "planned_start": args.planned_start, "planned_end": args.planned_end}
    if args.parent_task_id is not None:
        body["parent_task_id"] = int(args.parent_task_id)
    print(json.dumps(_request("POST", f"/api/plans/{args.plan_id}/tasks", body)["data"], indent=2, ensure_ascii=False))


def cmd_update_task(args):
    body = {}
    if args.name is not None:
        body["name"] = args.name
    if args.description is not None:
        body["description"] = args.description
    if args.planned_start is not None:
        body["planned_start"] = args.planned_start
    if args.planned_end is not None:
        body["planned_end"] = args.planned_end
    if args.completed is not None:
        body["is_completed"] = args.completed
    print(json.dumps(_request("PUT", f"/api/plans/{args.plan_id}/tasks/{args.task_id}", body)["data"], indent=2, ensure_ascii=False))


def cmd_complete_task(args):
    body = {"is_completed": True}
    print(json.dumps(_request("PUT", f"/api/plans/{args.plan_id}/tasks/{args.task_id}", body)["data"], indent=2, ensure_ascii=False))


def cmd_complete_plan(args):
    print(json.dumps(_request("POST", f"/api/plans/{args.plan_id}/complete"), indent=2, ensure_ascii=False))


def cmd_delete_task(args):
    print(json.dumps(_request("DELETE", f"/api/plans/{args.plan_id}/tasks/{args.task_id}"), indent=2, ensure_ascii=False))


def cmd_delete_plan(args):
    print(json.dumps(_request("DELETE", f"/api/plans/{args.plan_id}"), indent=2, ensure_ascii=False))


def cmd_indent_task(args):
    print(json.dumps(_request("POST", f"/api/plans/{args.plan_id}/tasks/{args.task_id}/indent")["data"], indent=2, ensure_ascii=False))


def cmd_outdent_task(args):
    print(json.dumps(_request("POST", f"/api/plans/{args.plan_id}/tasks/{args.task_id}/outdent")["data"], indent=2, ensure_ascii=False))


def cmd_move_task(args):
    body = {"direction": args.direction}
    print(json.dumps(_request("POST", f"/api/plans/{args.plan_id}/tasks/{args.task_id}/move", body), indent=2, ensure_ascii=False))


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("list", help="List study plans (incomplete only by default)")
    p.add_argument("--all", action="store_true", help="Include completed plans")
    p.set_defaults(func=cmd_list)

    p = sub.add_parser("plan", help="Get one plan with its tasks")
    p.add_argument("plan_id")
    p.set_defaults(func=cmd_plan)

    p = sub.add_parser("tree", help="Print a plan's WBS tree, human-readable")
    p.add_argument("plan_id")
    p.set_defaults(func=cmd_tree)

    p = sub.add_parser("create-plan", help="Create a new study plan")
    p.add_argument("name")
    p.add_argument("description")
    p.add_argument("start_date")
    p.add_argument("end_date")
    p.set_defaults(func=cmd_create_plan)

    p = sub.add_parser("update-plan", help="Update fields on an existing plan (only passed fields change)")
    p.add_argument("plan_id")
    p.add_argument("--name")
    p.add_argument("--description")
    p.add_argument("--start-date", dest="start_date")
    p.add_argument("--end-date", dest="end_date")
    g = p.add_mutually_exclusive_group()
    g.add_argument("--completed", dest="completed", action="store_true", default=None)
    g.add_argument("--incomplete", dest="completed", action="store_false")
    p.set_defaults(func=cmd_update_plan)

    p = sub.add_parser("create-task", help="Add a task (step) to a plan, optionally nested under a parent")
    p.add_argument("plan_id")
    p.add_argument("name")
    p.add_argument("description")
    p.add_argument("planned_start")
    p.add_argument("planned_end")
    p.add_argument("--parent-task-id", dest="parent_task_id")
    p.set_defaults(func=cmd_create_task)

    p = sub.add_parser("update-task", help="Update fields on an existing task (only passed fields change)")
    p.add_argument("plan_id")
    p.add_argument("task_id")
    p.add_argument("--name")
    p.add_argument("--description")
    p.add_argument("--planned-start", dest="planned_start")
    p.add_argument("--planned-end", dest="planned_end")
    g = p.add_mutually_exclusive_group()
    g.add_argument("--completed", dest="completed", action="store_true", default=None)
    g.add_argument("--incomplete", dest="completed", action="store_false")
    p.set_defaults(func=cmd_update_task)

    p = sub.add_parser("complete-task", help="Mark a task done")
    p.add_argument("plan_id")
    p.add_argument("task_id")
    p.set_defaults(func=cmd_complete_task)

    p = sub.add_parser("complete-plan", help="Mark a whole plan done")
    p.add_argument("plan_id")
    p.set_defaults(func=cmd_complete_plan)

    p = sub.add_parser("delete-task", help="Delete a task")
    p.add_argument("plan_id")
    p.add_argument("task_id")
    p.set_defaults(func=cmd_delete_task)

    p = sub.add_parser("delete-plan", help="Delete a plan")
    p.add_argument("plan_id")
    p.set_defaults(func=cmd_delete_plan)

    p = sub.add_parser("indent-task", help="Make a task the last child of its previous sibling")
    p.add_argument("plan_id")
    p.add_argument("task_id")
    p.set_defaults(func=cmd_indent_task)

    p = sub.add_parser("outdent-task", help="Make a task a sibling right after its old parent")
    p.add_argument("plan_id")
    p.add_argument("task_id")
    p.set_defaults(func=cmd_outdent_task)

    p = sub.add_parser("move-task", help="Reorder a task among its siblings")
    p.add_argument("plan_id")
    p.add_argument("task_id")
    p.add_argument("direction", choices=["up", "down"])
    p.set_defaults(func=cmd_move_task)

    args = parser.parse_args()
    try:
        args.func(args)
    except RuntimeError as e:
        print(json.dumps({"error": str(e)}), file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
