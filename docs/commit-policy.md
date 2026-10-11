# Commit policy

The canonical commit policy for this repository. It is referenced from
[`docs/development.md`](development.md), the README's contributing section and
`PROJECT_SPEC.md`; **this file is the single source of truth** and the others link
here rather than restating it.

It applies to human contributors and to AI agents working in this repository.

---

## The principle

**Optimise commits for clarity, reviewability, traceability and safe rollback —
not for file count.**

A development stage is a *unit of work*, not necessarily a single commit. Stages
regularly touch dozens of files across the backend, the frontend, the database
schema, the agent runtime, tests and documentation. Bundling all of that into one
commit because it happened on the same day makes the history unreviewable and
impossible to bisect.

Equally: do not manufacture commits to reach a target count. A one-line fix and
its test belong together.

---

## 1. Split by intent, not by file

Group changes that share a *reason*. Two changes belong in the same commit when
they would be described by the same sentence.

| Group together | Split apart |
|---|---|
| A bug fix and the test that proves it | A bug fix and an unrelated refactor noticed while fixing it |
| A schema migration and the code that reads the new column | A schema migration and a documentation spelling fix |
| A new API endpoint, its adapter, and its frontend caller | Two independent features that happen to land in one stage |
| A rename and every reference to the renamed thing | A rename and a behaviour change to the renamed thing |

**Keep changes that must work together in one commit.** A commit that leaves the
repository unable to start is worse than a large commit. If splitting would make
the tree inconsistent — a migration without its reader, an API change without its
caller — do not split it.

---

## 2. Order commits so each one is coherent

A useful default order for a stage, grouping by **functional boundary**:

1. `fix:` or `feat:` — backend behaviour (services, repositories, models)
2. `feat:` or `fix:` — API surface (routers, schemas)
3. `feat:` — frontend (components, state, hooks)
4. `test:` — tests that are not part of the change they cover
5. `docs:` — README, specification, `docs/`
6. `chore:` — tooling, dependencies, deployment
7. `docs:` — the project report for the stage

Tests normally travel with the change they cover (rule 1), so a separate `test:`
commit is for coverage that stands on its own.

---

## 3. Conventional Commits

Use a prefix that describes the *intent*:

| Prefix | Use for |
|---|---|
| `feat` | A new capability a user or another component can use |
| `fix` | Correcting broken behaviour |
| `refactor` | Restructuring with no behaviour change |
| `perf` | A change made specifically for speed |
| `test` | Tests only |
| `docs` | Documentation only |
| `chore` | Tooling, dependencies, build, deployment |
| `style` | Formatting only |

Rules for the message:

- **Subject** — imperative mood, lower case after the prefix, no trailing full
  stop, ≤ 72 characters. `fix: retrieve models without a chosen model`
- **Body** — explain *why*, not *what*. The diff shows what. Wrap at 72 columns.
- **Footer** — reference issues (`Refs: #12`) when relevant.

If a change is not obviously one prefix, that is usually a sign it should be two
commits.

---

## 4. Before every commit

```bash
# 1. Review what you are about to commit — the whole diff, not just the stat.
git diff --staged

# 2. Confirm nothing unintended is included.
git diff --staged --name-only | grep -Ei \
  '\.env$|^data/|master\.key|secrets\.enc|node_modules|/venv/|frontend/dist|\.db$'

# 3. Run the tests relevant to the change (all of them before a push).
cd backend && ../venv/bin/python -m pytest
cd frontend && npm test && npm run typecheck
```

**Never commit:** credentials or `.env`; anything under `data/` (the database, the
encryption key, encrypted secrets, workspaces, Solo's Pi runtime); `venv/`,
`node_modules/`, `frontend/dist/`; editor or OS files; and any change you did not
intend to make.

**Preserve unrelated local changes.** If the working tree contains work that is not
yours to commit, either leave it and stage selectively (`git add -p`, explicit
paths) or commit it separately as its own change with its own message. Never
sweep it into an unrelated commit with `git add -A`.

---

## 5. Record the verification

State what was run in the commit body when the change is more than trivial:

```
fix: retrieve models before a model is chosen

The model-list endpoint used the completion accessor, which requires both an API
key and a chosen model. Listing models is the step that comes before choosing
one, so in the normal first-run state the endpoint saw None and reported a
missing key.

Verified: 384 backend tests, 116 frontend tests, typecheck clean.
```

---

## 6. Pushing

- Push verified commits to the intended branch at sensible checkpoints — after a
  coherent group, not after every commit and not only at the very end.
- **Never rewrite shared history.** No `--force`, no `rebase` of pushed commits,
  no `commit --amend` of a commit that is already on the remote — without explicit
  authorisation.
- Never commit or push automatically where the repository workflow requires human
  approval.
- After pushing, confirm the branch is in sync and the remote is the intended one.

---

## 7. Checklist

Copy this into a stage's planning notes and tick it off:

```
[ ] Each commit has a single, describable intent
[ ] No commit leaves the tree unable to build or start
[ ] Staged diff reviewed in full
[ ] No secrets, data, generated files or unrelated changes staged
[ ] Conventional Commit subject, ≤ 72 chars, imperative
[ ] Body explains why; verification noted
[ ] Relevant tests run and passing
[ ] Pushed to the intended branch; no history rewritten
```
