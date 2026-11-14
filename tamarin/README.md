# Formal models

Tamarin models of the protocol. Checked with Tamarin 1.12.0 and Maude 3.5.1.

    tamarin/verify.sh

runs everything below and compares each result with the expected one (about three minutes).

## `agent_written_boundary.spthy`

The agent writes the boundary and the user approves it by signing.

    tamarin-prover --prove tamarin/agent_written_boundary.spthy

| Lemma | Result |
|---|---|
| `executable` | verified |
| `executed_was_approved` | verified |
| `executed_is_what_user_intended` | falsified |

Both signatures verify and the operation fits the signed boundary, yet the executed operation is not the one the user intended.

The attack requires that the user signs what the agent presents without comparing it to the intent. With `-D=user_compares` the user signs only a boundary equal to the intent, and all three lemmas are verified.

## `signed_template.spthy`

The user signs a template published by the service, and the service checks every operation against it. The agent signs any operation the attacker chooses, and the agent's key can be revealed. Rules can fire any number of times, so the results hold for any number of users, agents, templates and operations.

    tamarin-prover --prove tamarin/signed_template.spthy

| Lemma | Statement | Result |
|---|---|---|
| `executable` | Two operations can execute under one template. | verified |
| `executable_with_revealed_key` | With the agent's key revealed, an operation the agent never signed can execute. | verified |
| `confinement` | Every executed operation falls under a template the user signed: same scope, amount within the limit, routine, not expired. | verified |
| `count_not_exceeded` | The counter never passes the signed count. | verified |
| `count_each_unit_spent_once` | No two executions under one template share a counter value. | verified |
| `no_replay` | A signed operation executes at most once. | verified |
| `attribution` | Every executed operation was signed, for that template, by the agent the template names, unless that agent's key was revealed. | verified |

## Each condition is needed

Each condition of the service's check is one restriction in `signed_template.spthy`. A flag removes it:

    tamarin-prover --prove -D=without_c6 tamarin/signed_template.spthy

| Flag | Condition removed | Lemmas falsified | Attack found |
|---|---|---|---|
| `without_c1` | C1: the user's signature on the template is valid | `confinement`, `count_not_exceeded`, `attribution` | The service stores a template the user never signed and executes under it. |
| `without_c1_stored_once` | C1: a template is stored once | `count_each_unit_spent_once` | The same signed template is stored twice, which gives it two counters. |
| `without_c2` | C2: the operation is signed by the agent key the template names | `attribution` | An operation the agent never signed executes. |
| `without_c2_template_id` | C2: the signature covers the template identifier | `attribution` | An operation signed for one template executes under another. |
| `without_c3` | C3: the operation number has not been used before | `no_replay` | The same signed operation executes twice. |
| `without_c4_scope` | C4: the scope is the one in the template | `confinement`, `attribution` | An operation on a scope the template does not name executes. |
| `without_c4_amount` | C4: the amount is within the limit | `confinement` | An operation over the limit executes. |
| `without_c4_expiry` | C4: the template has not expired | `confinement` | An operation executes after the template expired. |
| `without_c5` | C5: the count is not used up | `count_not_exceeded` | More operations execute than the signed count. |
| `without_c6` | C6: the operation is not in the fresh-approval class | `confinement` | An operation that needs a fresh user approval executes under a template. |

With any one flag, all other lemmas remain verified.
