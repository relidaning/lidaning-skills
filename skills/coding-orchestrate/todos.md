# TODO.md

Things discovered during conversation that need doing. The file lives at the
project root as `TODO.md`. Add items as they come up naturally — never let a
task get lost in the chat.

## Format

```markdown
# TODOs

- [ ] Add rate limiting to auth endpoints
- [ ] Write unit tests for token validation
- [ ] Update API docs with new error codes
- [x] Create POST /auth/login endpoint
- [x] Add JWT middleware
```

## Rules

- **One file** — `TODO.md` at project root
- **Discovered, not planned** — add items as they surface during conversation.
  A bug you can't fix now, a refactor noticed mid-task, a missing test.
- **Add immediately** — when the user or you discovers something that needs
  doing later, add it right then. Don't rely on remembering.
- **Mark done promptly** — when a task completes, check it off
- **Don't duplicate** — check the existing list before adding
- **Keep it visible** — after updating, show the user the current list unless
  they're mid-flow
- **Delete when empty** — if all items are done, remove the file
