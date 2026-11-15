# Templates

`catalog.json` lists the templates a service publishes and the operations that always need a fresh approval.

`labels.json` labels every state-changing operation in the reference solution of each AgentDojo user task (benchmark v1.2.2). Tasks that change no state are not listed.

## Labels

A template is signed before the agent runs, so it can hold only values the user has at that moment. Each labeled operation names the template it would use and records the source of every value the boundary needs.

| Source | Meaning |
|---|---|
| `stated` | The value is in the user's request. |
| `looked-up` | The request names something that the service resolves in the user's own records. |
| `computed` | The agent works the value out from the service's records. |
| `content` | The agent reads the value from content that another party can write. |

Each target has a `role` (payee, recipient, invitee, file, and so on) and the `value` as the user gives it. Where the service displays something else for signing, `resolved` holds it: the identifiers a looked-up name resolves to, or a stated value in the form the tool uses. A payee the user names, such as Spotify, resolves to its account in the user's transaction history and to the name itself, because AgentDojo's reference solutions pay the name.

`action` is `content` when the request leaves the choice of operation to content, as in "do what the email says". `amount` is recorded only where the operation moves money.

## Decision

An operation needs a fresh approval if any of the following holds; otherwise it runs inside its template.

1. Its tool is in `always_fresh`.
2. Its action comes from content.
3. One of its targets is computed or comes from content.
4. Its amount comes from content.

The approvals a task needs are the templates it signs plus its fresh approvals.

## Reproducing the coverage table

    uv run python -m poia_agents.coverage
    uv run pytest tests/test_coverage.py

The test checks that the labeled operations match AgentDojo's reference solutions tool by tool, that every value labeled `stated` appears in the request, and that the totals equal those reported in the paper.
