# Decision data contract (version 1)

Runtime layout, all relative to the selected data root (default
`<app-root>/data/evolvingme/`, resolved as described in `../SKILL.md`):

```text
decisions/<domain>.jsonl
principles/<domain>.jsonl
domains/<topic-slug>/principles.md
```

Use one domain file for related decisions, such as `coding.jsonl` or
`layout.jsonl`. Reuse existing domain slugs instead of creating near-duplicates;
the filename's domain must match `scope.domain`. Keep one primary domain per
decision and retain project scope inside each record. Principles use the same
domain organization in their separate directory. Indexes link IDs and files,
not line numbers, which may change during recovery or deletion.

Use UUIDs for IDs and revision IDs, UTC ISO 8601 timestamps, UTF-8 JSONL,
and the schema beside this file for each line. Each revision is one complete
JSON object on one line, followed by a newline; escape embedded newlines.
Validate before appending. Create the domain file if absent, otherwise append
without truncating existing records. Serialize writers using an exclusive
per-domain lock covering read/check/append, including migrations and repairs;
all writers must use the same lock (for example `<data-root>/.locks/<domain>.lock`
with an OS advisory file lock). Flush and fsync before reporting success.
Under the lock, check revision IDs: identical existing revisions are idempotent
retries; a reused ID with different content is an error. Validate the predecessor
and current head before appending a superseding revision.

If the last line is incomplete or invalid after an interrupted write, stop
appending and report the blocker; do not append onto a damaged tail or silently
discard evidence. Readers may use valid earlier lines but must disclose partial
coverage. Repair only within authorized scope. Explicit forget/delete requests
are an exception to append-only storage: rewrite affected files atomically under
the same lock, removing affected revisions and derived data without backups of
forgotten content. A revision's
`supersedes` is its predecessor revision ID, or null on creation. Do not change
IDs when a pending decision is confirmed.

Records form revision chains. The current revision is the sole unsuperseded
head, not simply the last line or newest timestamp. Multiple heads mean a
concurrent-update conflict: preserve both and resolve explicitly before
export or synchronization. Indexes are rebuildable navigation, never evidence.
Each domain notebook lists record IDs, a short scope, active principle IDs,
and the owning skill or proposed skill purpose. Avoid copying raw records.

To migrate legacy per-revision JSON files, validate each record and append it to
the matching domain file under the same lock, preserving IDs, revisions,
timestamps, provenance and supersedes links. Verify persisted records before
removing their authorized legacy copies. Reclassification appends a superseding
revision with the new domain; preserve its predecessor in the old domain and
update the index to link both files. A layout-only migration leaves the per-line
schema version at 1.

Decision `payload` fields:

| Field | Contract |
| --- | --- |
| `status` | `pending`, `confirmed`, or `declined` |
| `situation`, `question` | Minimal context available before the answer |
| `options` | Objects with stable `id` and `summary`; empty if open-ended |
| `constraints` | Known constraints; no invented constraints |
| `prediction` | Null or `{text, confidence, evidence_ids}`; confidence is low/medium/high, not an uncalibrated probability |
| `choice` | Null while pending; otherwise summary of actual user answer |
| `user_rationale` | User-stated reason or null |
| `agent_interpretation` | Separate inference or null |
| `principle_ids` | Linked derived principles, possibly empty |

Principle `payload` fields:

| Field | Contract |
| --- | --- |
| `statement` | Actionable scoped preference |
| `status` | `active`, `tentative`, or `retired` |
| `basis` | `explicit` or `inferred` |
| `conditions`, `exceptions` | Lists preserving applicability boundaries |
| `evidence_ids`, `counterevidence_ids` | Decision IDs supporting/challenging this principle |
| `sync` | List of `{target, summary, status}`; status applied/pending/conflict/failed |

Every record has `source` with `kind` (`user` or `agent`), `locator` (message
reference or null), and `summary` (minimal redacted source evidence). Pending
agent predictions use kind agent; confirmed decisions require kind user.
`scope` holds `project` (stable project identifier or null for general),
`domain` (topic slug) and `conditions` (list). Null project does not make a
situational preference universal. `created_at` timestamps the revision.

For training, export only when requested to an authorized destination. Use
one JSONL row per current confirmed decision, with `decision_id`, `input`
(pre-answer situation/question/options/constraints), `prediction`, `label`
(user choice), `user_rationale`, `scope`, `source`, and linked `principle_ids`.
Exclude pending/declined records, unresolved revision conflicts and retired
labels. Do not place the answer, later principles or hindsight in `input`.
Keep provenance and schema version; never label agent predictions as user
choices. Group revisions and related project/session examples into the same
training split to avoid leakage. Human review, consent to actual training,
redaction and split design remain necessary before a model-training run.

Behavior checks with synthetic conversations (do not store these as user data):

- No history + a clarification: pending decision and tentative brain block;
  no invented preference.
- User chooses B because it works offline: same ID confirmed, rationale
  preserved; no global offline rule unless the user says it is reusable.
- User says “Always prefer offline tools for my private notes”: explicit
  scoped principle; update the owning skill, with a synchronization outcome.
- User answers only one of two questions: only that choice is confirmed.
- User reverses a choice: append a revision and preserve the earlier prediction;
  no contradictory active rule is silently applied.
- No owning skill: write the domain notebook, no surprise skill installation.
- Storage/edit failure: disclose unsaved/pending changes; no success claim.
- Unsolicited "I think it should be in app-root/data/evolvingme/": create a
  confirmed scoped choice without a prior question; verify persistence and show
  the recording receipt, without inferring a global storage rule.
- "Organize decisions by domain and append to the existing file": record the
  organization choice in the same turn as the implementation and show a receipt.
- "Update EvolvingMe's trigger and show its format when it records": record
  this explicit user choice once; internal bookkeeping creates no extra records.
- "What is JSONL?": answer without creating a preference or recording receipt.
- "Would JSONL or SQLite be better?": discussion only; no confirmed choice
  until the user actually chooses. A recorded pending revision gets a pending
  receipt, never a confirmed one.
