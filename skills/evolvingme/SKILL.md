---
name: evolvingme
description: >
  Use before asking the user for a decision or clarification, and whenever the
  user chooses, approves, rejects, corrects, or specifies an approach, convention,
  storage layout, workflow, or preference, even without a prior question.
  Includes "I think it should...", "use X instead", and requests to change skill
  rules or triggers. Record scoped decisions and show a brain-framed receipt
  after verified writes; recall principles and offer instincts before questions.
---

# EvolvingMe

Learn how this user decides, preserving evidence for future decision-model
training. Phase one advises; the user remains the decision maker. Do not ask
extra questions just to collect data or replace the agent's actual task.

## Activation and turn completion

User-confirmed principle `2a67b2fb-c7d5-476b-84f7-273c51a35a8e`:
capture unsolicited choices and visibly confirm saves so decisions are not
lost while their implementation is completed.

- A decision need not answer an agent question or state a permanent rule.
  Unsolicited design choices, corrections and concrete change requests specifying
  a chosen behavior count. For example, "it should be in app-root/data/..."
  and "organize decisions by domain and append to the existing file" trigger
  recording in the same turn, alongside implementing the requested change.
- Do not treat every message as a decision: information-only questions, quoted
  examples, agent proposals, and routine execution requests with no new choice
  do not establish a preference. Tentative alternatives posed for discussion
  remain unresolved; do not turn them into confirmed choices.
- A concrete "I think it should..." instruction may express a current choice
  without creating a universal principle. Preserve the actual scope and wording;
  do not require the user to say "remember" or invoke this skill explicitly.
- Before ending an applicable turn, verify that each expressed choice has a
  validated, persisted revision and an updated domain index, or disclose the
  specific unsaved work. Editing a skill or implementing a choice alone does
  not record the decision. Explicit user requests about EvolvingMe itself count;
  internal recording, index updates and receipts do not recursively create
  further decisions.

## Storage and access

Use `<app-root>/data/evolvingme/` by default. Resolve installation symlinks
first: when the real skill folder is `<app-root>/skills/evolvingme/`, app root
is the parent of `skills/` (the distribution repository root), not the project
the agent is currently working on. For this deployment the default is
`/data/apps/lidaning-skills/data/evolvingme/`. For another installation layout,
select an absolute `EVOLVINGME_DATA_DIR` explicitly rather than guessing a root.
An explicitly selected absolute `EVOLVINGME_DATA_DIR` overrides the default;
reject relative overrides. Use the same root across agents; project scope is
recorded inside records, not inferred from the caller's cwd. Create directories
only when needed. Never commit runtime records; ignore the selected data root.
Existing records under the former `skills/evolvingme/data/` location require
an explicit migration preserving IDs and revisions; changing the default does
not move or merge them automatically.

This request authorizes the decision-memory workflow when invoked, within the
conversation and stated scope. Respect applicable private-data permissions:
do not crawl chat histories, vaults, credentials or unrelated files. Obtain
permission if required for a new data source or destination. Exclude secrets
and unnecessary personal details; use minimal redacted summaries. Exporting
data or training a model is a separate operation requiring user authorization.
Do not claim that local storage is encrypted or technically access controlled.

Read [the record contract](references/records.md) before writing records and
[SQLite usage](references/sqlite.md) for commands, migration and recovery.
SQLite is the default storage interface: `<data-root>/evolvingme.sqlite3`.
Use `scripts/store.py` relative to the real skill source; send complete revisions
on stdin, never in shell arguments. It validates the existing JSON schema and
atomically appends revisions and updates the indexed head view. Never directly
edit database rows or overwrite earlier revisions. No service or paid session
is needed. The Guardails standing allowlist covers this minimal local workflow.

Legacy JSONL files are migration inputs, not a parallel writable backend.
Before first recording against an existing root, explicitly import its
`decisions/` and `principles/` files with `import-jsonl <data-root>`. Imports are
transactional and idempotent; originals remain untouched. Do not silently read
or migrate former roots. A root containing legacy records must be imported
before recall or append, so older evidence is not silently omitted.

## Before asking for instructions

1. Summarize the situation, decision question, realistic options and constraints
   already known. Assign a stable decision ID; record a pending revision before
   asking. Do not invent alternatives or reasons that were never available.
2. Recall relevant confirmed decisions and active principles for this project
   and domain. Query indexed current heads with `list --domain <domain>`, then use
   `list --id <id>` for linked records; do not scan every domain.
   Preserve conditions and exceptions. An explicit current instruction wins;
   prefer specific applicable scope over general defaults. Surface unresolved
   conflicts instead of silently treating recency as a universal override.
3. Form a short instinct: predicted preference, evidence IDs and uncertainty.
   With no relevant evidence, say this is a tentative suggestion based on the
   current situation. Agent suggestions never become user-preference evidence.
4. Ask the necessary question in the host's supported interface. Under the
   agent's normal response, append exactly this block (literal brain emoji):

   🧠
   EvolvingMe: <short instinct, reason, and uncertainty when relevant>
   🧠

   If questions must use a dedicated tool, put the block in the accompanying
   response text; do not repeat the question in a forbidden channel. Keep it
   below the main response, including any required language-practice block.
   Never show a prediction as a decision already made by the user.

## After the user decides

1. Match the answer to its pending decision by context/ID. Split independent
   choices into separate records. Leave unanswered choices pending; record an
   explicit refusal or cancellation as declined. Silence is never confirmation.
   If the answer is ambiguous, retain pending status and clarify only what is
   necessary. If there was no prior question, create a decision record directly.
2. Append a new revision with the actual choice and source message locator
   (or a clearly marked unavailable locator plus minimal source summary), the
   user's stated rationale, and any correction. Unknown rationale is null;
   separate agent interpretation from user statements. Link revisions rather
   than overwriting history. Record the instinct before the answer, so hindsight
   cannot contaminate prediction evaluation.
3. Distill a principle only when the user explicitly states a reusable rule,
   or repeated confirmed choices support a tentative inference. A single
   situational choice stays situational. Label inferred principles tentative;
   preserve supporting decision IDs, scope, exceptions and counterevidence.
   Never promote an inference to explicit confirmation without user evidence.
4. Verify the saved revision with `list --id <id>`; the database head view
   is the automatically updated domain index. Maintain domain notebooks for
   ownership and fallback principles where needed. Briefly tell the
   user what was learned and which related skill changed or remains pending.
   Use the required recording receipt below, even when no question was asked.

## Required recording receipt

Whenever this turn persists a decision or principle revision, verify the saved
record and append this block below the main response, including any required
language-practice block. Use one receipt for the turn, listing each affected
domain/file and ID when multiple records were written:

🧠
EvolvingMe: Recorded — <short summary of the choice; pending/confirmed/declined or principle status>.
Domain: <domain> | File: evolvingme.sqlite3 (revision <revision ID>) | ID: <record ID>
Skill sync: <target and applied/pending/conflict/failed, or not applicable>.
🧠

Show the receipt for backfills and corrections too. If a question's instinct
block is also needed, combine the instinct and receipt inside one brain frame,
labeling the instinct separately from the saved choice. A receipt confirms
persistence, not activation alone or successful implementation. On failed or
blocked writes, use `EvolvingMe: Not recorded — <reason>` in the same frame
and identify any partial success precisely. Routine answers with neither a
write nor a decision question need no block.

## Synchronize related skills

Find the owning installed skill by its description and read its instructions.
Edit its real source once, not each agent's symlink. Only propagate confirmed,
reusable user principles, within their scope and existing editing permissions.
Keep speculative principles in EvolvingMe. Repeated choices alone do not
authorize turning a tentative inference into a rule in another skill.

Make a narrow change where that skill keeps its own rules; include a concise
reason and stable principle ID, never private conversation dumps. Preserve
existing permissions, safety boundaries and unrelated conventions. Read the
current rule before editing; do not overwrite concurrent changes. Validate the
skill after changes using available validation tools or structural/manual checks.
Record the target, summary and outcome (applied, pending, conflict or failed).
If editing is blocked, retain the concrete proposed change locally and report
the blocker without claiming synchronization succeeded. Retry only after the
blocker changes. Do not recursively trigger EvolvingMe on its own bookkeeping.

If no skill owns the topic, create `domains/<topic-slug>/principles.md`
relative to the selected data root. Include scoped principles,
evidence IDs and candidate skill purpose/triggers. This is a domain notebook,
not a newly installed skill; create/register a full skill only when requested.
Keep this fallback even when a future skill owns the topic, pointing to its
owner rather than maintaining duplicate authoritative rules.

## Honesty and lifecycle

This skill works only when the host loads it; it cannot intercept all questions
or persist after a session ends by itself. Save updates during the active turn.
Do not modify global agent instructions or install hooks to force activation.
If storage is unavailable, continue the user's task and disclose the unsaved
update; never pretend memory was written. Corrections append superseding
revisions. Explicit forget/delete requests use `forget <id>` for all affected IDs and
remove affected source records,
derived principles and exports within authorized scope, and reconcile rules
propagated to other skills. Preserve no copy of forgotten content in an audit
entry; report any destination that cannot be cleaned up.
