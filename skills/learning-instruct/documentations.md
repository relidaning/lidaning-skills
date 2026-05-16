# DOCUMENTATIONS.md

An index of external resources the user provided (URLs, documents) that have
been summarized into individual files under `.learning-instruct/docs/`.
Lives at `.learning-instruct/DOCUMENTATIONS.md`.

Each resource gets its own file: `.learning-instruct/docs/<document_name>.md`.

## Format

```markdown
# Documentations

| Name | Source | File | Added |
|---|---|---|---|
| TypeScript Handbook — Generics | https://www.typescriptlang.org/docs/handbook/2/generics.html | docs/typescript-handbook-generics.md | 2026-05-16 |
| Effective TypeScript Item 43 | user-provided PDF | docs/effective-ts-item-43.md | 2026-05-16 |
```

## Document file format

Each `.learning-instruct/docs/<name>.md` should be a faithful summary of
the source material:

```markdown
# <Title>

**Source:** <URL or "user-provided [format]">
**Added:** 2026-05-16

## Summary

<concise summary of the resource's content, in its own terms>

## Key points

- <point 1>
- <point 2>

## Notes

<optional — how this relates to the user's learning goal, if the resource
itself makes that connection clear>
```

## Rules

- **Write files to disk, always** — the summary must be a real file under
  `.learning-instruct/docs/`. Create the directory if it doesn't exist.
  Chat text is not enough — the user must be able to `ls` and `cat` the
  file. If there's no file, the ingestion didn't happen.
- **Source content only** — summarize what the resource actually says. Do
  NOT add explanations, context, or corrections from your own knowledge.
  The point is to capture the source faithfully, not to teach around it.
- **One file per resource** — don't cram multiple URLs into one file
- **Index immediately** — when a summary is written, add a row to
  DOCUMENTATIONS.md right away and write that file too
- **Name files descriptively** — `docs/typescript-generics-handbook.md` not
  `docs/doc1.md`. Derive the name from the resource title or topic.
- **User triggers this** — the user must provide a URL or document. Don't
  go sourcing documents on your own initiative.
- **Link back to goal** — if the resource explicitly relates to the user's
  learning goal, note the connection in the Notes section
