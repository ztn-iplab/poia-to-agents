# poia-to-agents

Proof-of-Intent Authorization (PoIA) for LLM agents.

An LLM agent that reads untrusted content (emails, files, web pages) can be steered by prompt injection into actions the user never asked for. PoIA binds each sensitive tool call to an intent the user committed to before the agent saw any untrusted data, and the tool (the relying party) verifies that binding before it executes anything.

This repository builds PoIA as a defense layer and evaluates it on the [AgentDojo](https://github.com/ethz-spylab/agentdojo) benchmark. It also holds the Tamarin model of the protocol.

## Layout

| Folder | What it holds |
|---|---|
| `src/poia_agents/intent/` | Intent schema and hand-written intent specs |
| `src/poia_agents/crypto/` | Commitments and signatures (user-device key) |
| `src/poia_agents/pipeline/` | PoIA layers that plug into AgentDojo pipelines |
| `src/poia_agents/attacks/` | Adaptive attacks aimed at PoIA |
| `scripts/` | Benchmark runner and trace replay |
| `tutorials/` | Step-by-step learning scripts |
| `tamarin/` | Formal model of agent-mediated PoIA |
| `results/` | Run outputs (not tracked in git) |

## Setup

Requires [uv](https://docs.astral.sh/uv/).

    uv sync
    uv run pytest

## Relation to AgentDojo

AgentDojo is used unmodified, as a pinned dependency (`agentdojo==0.1.35`, benchmark version `v1.2.2`). All PoIA code lives in this repository and plugs in through AgentDojo's public extension points.

AgentDojo is MIT-licensed. If you use this work, please also cite:

    @inproceedings{debenedetti2024agentdojo,
      title     = {AgentDojo: A Dynamic Environment to Evaluate Prompt Injection Attacks and Defenses for {LLM} Agents},
      author    = {Edoardo Debenedetti and Jie Zhang and Mislav Balunovic and Luca Beurer-Kellner and Marc Fischer and Florian Tram{\`e}r},
      booktitle = {The Thirty-eighth Conference on Neural Information Processing Systems Datasets and Benchmarks Track},
      year      = {2024}
    }
