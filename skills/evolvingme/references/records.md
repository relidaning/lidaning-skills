# Decision data contract (version 1)

Runtime layout, all relative to the selected data root:

```text
decisions/<decision-id>/<revision-id>.json
principles/<principle-id>/<revision-id>.json
domains/<topic-slug>/principles.md
```

Use UUIDs for IDs and revision filenames, UTC ISO 8601 timestamps, UTF-8 JSON,
and the schema beside this file. Create each revision as a new file with
exclusive creation or a temporary file followed by an atomic move without
overwriting an existing revision. Validate JSON and required fields before
publishing it. Incomplete temporary files are not records. A revision's
`supersedes` is its predecessor revision ID, or null on creation. Do not change
IDs when a pending decision is confirmed.

Records form revision chains. The current revision is the sole unsuperseded
head, not simply the last filename alphabetically. Multiple heads mean a
concurrent-update conflict: preserve both and resolve explicitly before
export or synchronization. Indexes are rebuildable navigation, never evidence.
Each domain notebook lists record IDs, a short scope, active principle IDs,
and the owning skill or proposed skill purpose. Avoid copying raw records.

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
