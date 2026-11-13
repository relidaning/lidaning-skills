---
name: evolvingme
description: >
  Use when an agent asks the user for a decision, preference, clarification or
  instructions, and when the user answers, corrects a choice or states a lasting
  preference. Record decision context and confirmed choices, recall scoped
  principles, suggest an EvolvingMe instinct, and update related skills.
---

# EvolvingMe

Learn how this user decides, preserving evidence for future decision-model
training. Phase one advises; the user remains the decision maker. Do not ask
extra questions just to collect data or replace the agent's actual task.

## Storage and access

Resolve paths relative to this skill's real source folder, including through
installation symlinks. Use `data/` there by default; an explicitly selected
absolute `EVOLVINGME_DATA_DIR` overrides it. Use the same root across agents;
project scope is recorded inside records, not inferred from the caller's cwd.
Create directories only when needed. Never commit runtime records.

This request authorizes the decision-memory workflow when invoked, within the
conversation and stated scope. Respect applicable private-data permissions:
do not crawl chat histories, vaults, credentials or unrelated files. Obtain
permission if required for a new data source or destination. Exclude secrets
and unnecessary personal details; use minimal redacted summaries. Exporting
data or training a model is a separate operation requiring user authorization.
Do not claim that local storage is encrypted or technically access controlled.

Read [the record contract](references/records.md) before writing records. The
machine contract is [record.schema.json](references/record.schema.json).
Use ordinary file tools; no service, paid session or background process is
required. File records are the storage interface; switching to a database needs
an importer preserving IDs, provenance and revisions, not just a path change.

## Before asking for instructions

1. Summarize the situation, decision question, realistic options and constraints
   already known. Assign a stable decision ID; record a pending revision before
   asking. Do not invent alternatives or reasons that were never available.
2. Recall relevant confirmed decisions and active principles for this project
   and domain. Read the domain index first, then only linked relevant records.
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
4. Update the relevant domain index with record/principle IDs. Briefly tell the
   user what was learned and which related skill changed or remains pending.
   Do not add an instinct block to routine answers with no decision request.

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

If no skill owns the topic, create `data/domains/<topic-slug>/principles.md`
inside EvolvingMe (or the configured data root). Include scoped principles,
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
revisions. Explicit forget/delete requests remove affected source records,
derived principles and exports within authorized scope, and reconcile rules
propagated to other skills. Preserve no copy of forgotten content in an audit
entry; report any destination that cannot be cleaned up.
