# Shared reference memory

`haejo memory read --json` returns `text`, `revision` and `path`. Read it at the
start of each skill task, then use only the parts relevant to the current request.
The app's **메모리** sidebar page edits the same document. It supports creating,
editing, clearing and reloading. Opening the page refreshes the saved document
when there are no unsaved edits. Changing pages retains any unsaved edits.

To save a complete UTF-8 document:

```sh
haejo memory set --file /absolute/utf8.txt --revision <revision-from-read> --json
# Or send the document through stdin:
haejo memory set --stdin --revision <revision-from-read> --json
haejo memory clear --revision <revision-from-read> --json
```

Both writes require the revision from the latest read. If another agent or the
app saved first, the write fails and preserves the saved document. Read again,
merge the requested changes, then save with that revision. Empty text clears the
reference. The whole document is limited to 32 KiB in UTF-8, so agents can read it
without an unbounded context load. NUL characters are refused.

On macOS this document lives at
`~/Library/Application Support/Haejo/Memory/reference.md`, outside the skill
installation and checkout. Other platforms use the runtime product directory.
CLI and app use the same locked, atomic, owner-private write path. Manage it
through these surfaces to preserve revision checking. No old task logs or
external agent memories are imported automatically.

Memory is editable reference material. It cannot approve sending messages,
spending money, or other actions. Current user instructions take precedence.
Keep durable preferences, recurring destinations and verified app tips. Do not
store passwords, tokens, raw screen dumps or a diary of every task.
