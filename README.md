# poia-to-agents

Proof-of-Intent Authorization (PoIA) for autonomous AI agents.

A user approves, once, a signed boundary on what an agent may do. The service checks every operation the agent requests against that boundary before executing it, so an operation outside the boundary is refused even when the agent has been manipulated, for example by prompt injection.

The design is evaluated on the [AgentDojo](https://github.com/ethz-spylab/agentdojo) benchmark.

## Setup

Requires [uv](https://docs.astral.sh/uv/).

    uv sync
    uv run pytest

## Contents

- `tamarin/`: the Tamarin models and the script that checks them.
- `templates/`: the template list and the label of every AgentDojo user task.
- `src/poia_agents/coverage.py`: the coverage of the tasks by the templates.
- `src/poia_agents/check.py`: the check a service runs before it executes an operation. `tests/test_check.py` has one test for each condition, matching the flags in `tamarin/README.md`.
- `src/poia_agents/effects.py`: what each AgentDojo tool call affects, its targets and its amount.
- `src/poia_agents/guard.py`: a simulated user who signs the templates of a task and approves fresh operations, and a runtime that asks the service before every state-changing tool call.
- `src/poia_agents/harness.py`: runs one AgentDojo case, with or without the check, and judges only the operations that executed.
- `src/poia_agents/replay.py`: the reference solutions and the reference attacks of AgentDojo replayed through the check, without an LLM.
- `src/poia_agents/experiment.py`: an LLM agent on one suite, with and without the check, under AgentDojo's `important_instructions` attack. Each case is saved under `results/`.

To reproduce the coverage table and the replay:

    uv run python -m poia_agents.coverage
    uv run python -m poia_agents.replay

To run an LLM agent, put `OPENAI_API_KEY` in `.env` and run, for example:

    uv run python -m poia_agents.experiment --model gpt-6-luna --suite banking

## AgentDojo

AgentDojo is used unmodified, as a pinned dependency (`agentdojo==0.1.35`). It is MIT-licensed:

    @inproceedings{debenedetti2024agentdojo,
      title     = {AgentDojo: A Dynamic Environment to Evaluate Prompt Injection Attacks and Defenses for {LLM} Agents},
      author    = {Edoardo Debenedetti and Jie Zhang and Mislav Balunovic and Luca Beurer-Kellner and Marc Fischer and Florian Tram{\`e}r},
      booktitle = {The Thirty-eighth Conference on Neural Information Processing Systems Datasets and Benchmarks Track},
      year      = {2024}
    }
