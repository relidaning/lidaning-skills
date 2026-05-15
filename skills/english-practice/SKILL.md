---
name: english-practice
description: >
  Correct non-native or awkward English expressions in the user's messages.
  Use when the user writes anything in English — check for grammar mistakes,
  awkward phrasing, unnatural word choices, or incorrect sentence structure.
---

## Instructions

1. When the user writes something grammatically wrong, awkwardly phrased, or
   with an unnatural word choice, briefly note the correction.
2. Keep corrections short — one sentence. Do not derail the conversation.
3. This correction comes before the result of your responding to user's request.
4. Format:

   === English Correction ===
   😂 original text
   😃 corrected text

   One-sentence reason why.
   === English Correction ===

   Here are what you response to user's ask.

5. Do NOT correct if:
   - The meaning is clear and the issue is trivial (a missing comma)
   - The user is in the middle of a fast back-and-forth
   - The user explicitly asks you not to

## Examples

=== English Correction ===
😂 please tell me how can I deploy this app.
😃 please tell me how I can deploy this app.

😜 You should use declarative word order in declarative sentences.
=== English Correction ===

You build it by docker and you can access it and test it.

```bash
cd /path/to/target && docker compose up -d --build
```
