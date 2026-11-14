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

To reproduce the coverage table:

    uv run python -m poia_agents.coverage

## AgentDojo

AgentDojo is used unmodified, as a pinned dependency (`agentdojo==0.1.35`). It is MIT-licensed:

    @inproceedings{debenedetti2024agentdojo,
      title     = {AgentDojo: A Dynamic Environment to Evaluate Prompt Injection Attacks and Defenses for {LLM} Agents},
      author    = {Edoardo Debenedetti and Jie Zhang and Mislav Balunovic and Luca Beurer-Kellner and Marc Fischer and Florian Tram{\`e}r},
      booktitle = {The Thirty-eighth Conference on Neural Information Processing Systems Datasets and Benchmarks Track},
      year      = {2024}
    }
