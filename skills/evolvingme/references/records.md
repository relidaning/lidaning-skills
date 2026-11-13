# Decision data contract (version 1)

Runtime storage is `<data-root>/evolvingme.sqlite3`; see [SQLite usage](sqlite.md).
The complete revision JSON shape remains version 1 and is validated against
`record.schema.json` including UUID and timestamp formats. Domain notebooks
remain at `domains/<topic-slug>/principles.md`.

Use UUIDs for record and revision IDs and UTC ISO 8601 revision timestamps.
Each revision is a complete object. `supersedes` is its predecessor revision ID,
or null on creation. Confirming a pending decision preserves its record ID.

The helper uses `BEGIN IMMEDIATE` to serialize writers and `synchronous=FULL`
for commits. Identical revision retries are idempotent; reused revision IDs with
different content fail. Updates must supersede the current head of the same ID
and kind, including domain reclassification. A stale writer fails instead of
creating a branch. The indexed `heads` view is rebuildable navigation, not
additional evidence, and changes atomically with each revision.

Legacy domain JSONL imports validate every record, domain, kind and revision
chain and preserve complete bodies including IDs, provenance and timestamps.
They run in one transaction, order predecessors before successors, reject
conflicts or incomplete/invalid lines, and leave source files untouched. Repeated
imports are safe. Do not remove legacy originals without authorization; after
cutover they are historical copies and must also be reconciled on forget requests.

Explicit forget requests are an exception to append-only evidence. Delete all
revisions for each affected ID with `forget`, then reconcile derived principles,
notebooks, authorized legacy copies and any authorized exports. SQLite uses
secure_delete with rollback journals; this does not promise erasure from backups,
filesystem snapshots or storage hardware. No audit payload retains deleted data.

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
