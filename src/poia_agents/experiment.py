"""Runs an LLM agent on an AgentDojo suite with and without the check, and records every case."""

import argparse
import json
from collections import Counter
from pathlib import Path
from types import SimpleNamespace

import openai
from agentdojo.agent_pipeline import (
    AgentPipeline,
    InitQuery,
    OpenAILLM,
    SystemMessage,
    ToolsExecutionLoop,
    ToolsExecutor,
)
from agentdojo.agent_pipeline.agent_pipeline import load_system_message
from agentdojo.attacks.base_attacks import FixedJailbreakAttack
from agentdojo.attacks.important_instructions_attacks import ImportantInstructionsAttack
from agentdojo.task_suite.load_suites import get_suite
from dotenv import load_dotenv

from poia_agents.coverage import BENCHMARK_VERSION, SUITES
from poia_agents.harness import open_session, run

RESULTS = Path("results")
ROWS = (
    "tasks without attack",
    "  solved",
    "cases under attack",
    "  user task solved",
    "  attack succeeds",
    "operations: allowed by a template",
    "operations: approved by the user",
    "operations: refused",
    "LLM calls",
    "input tokens",
    "output tokens",
)


class Metered:
    def __init__(self, client):
        self.calls = self.input = self.output = 0
        self.create = client.chat.completions.create
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self.count))

    def count(self, **request):
        completion = self.create(**request)
        self.calls += 1
        self.input += completion.usage.prompt_tokens
        self.output += completion.usage.completion_tokens
        return completion

    def reading(self):
        return Counter(calls=self.calls, input=self.input, output=self.output)


class Injection(ImportantInstructionsAttack):
    def __init__(self, suite, agent, model_name):
        FixedJailbreakAttack.__init__(self, self._JB_STRING, suite, agent)
        self.user_name = "Emma Johnson"
        self.model_name = model_name


def spoken_name(model):
    family, _, rest = model.partition("-")
    return f"GPT-{rest.split('-')[0]}" if family == "gpt" else family.capitalize()


def build_agent(llm):
    loop = ToolsExecutionLoop([ToolsExecutor(), llm])
    return AgentPipeline([SystemMessage(load_system_message(None)), InitQuery(), llm, loop])


def run_case(suite_name, task_id, injection_id, agent, attack, check, meter=None):
    suite = get_suite(BENCHMARK_VERSION, suite_name)
    task = suite.user_tasks[task_id]
    injection = suite.injection_tasks[injection_id] if injection_id else None
    injections = attack.attack(task, injection) if injection else None
    session = open_session(suite_name, task_id) if check else None
    before = meter.reading() if meter else Counter()
    solved, attacked, messages = run(suite_name, task, agent, injection, session, injections)
    used = (meter.reading() if meter else Counter()) - before
    return {
        "suite": suite_name,
        "user_task": task_id,
        "injection_task": injection_id,
        "check": check,
        "solved": bool(solved),
        "attacked": bool(attacked),
        "outcomes": session.outcomes if session else [],
        "calls": used["calls"],
        "input_tokens": used["input"],
        "output_tokens": used["output"],
        "messages": messages,
    }


def summarize(records):
    columns = {False: Counter(), True: Counter()}
    for record in records:
        column = columns[record["check"]]
        outcomes = Counter(outcome for _, outcome in record["outcomes"])
        if record["injection_task"] is None:
            column["tasks without attack"] += 1
            column["  solved"] += record["solved"]
        else:
            column["cases under attack"] += 1
            column["  user task solved"] += record["solved"]
            column["  attack succeeds"] += record["attacked"]
        column["operations: allowed by a template"] += outcomes["template"]
        column["operations: approved by the user"] += outcomes["fresh"]
        column["operations: refused"] += outcomes["refused"]
        column["LLM calls"] += record["calls"]
        column["input tokens"] += record["input_tokens"]
        column["output tokens"] += record["output_tokens"]
    return columns


def show(records):
    columns = summarize(records)
    print(f"\n{'':<36}{'no check':>14}{'with check':>14}")
    for row in ROWS:
        print(f"{row:<36}{columns[False][row]:>14}{columns[True][row]:>14}")
    for record in records:
        if record["check"] and record["attacked"]:
            print(f"attack succeeded with the check: {record['user_task']} {record['injection_task']}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", required=True)
    parser.add_argument("--suite", default="banking", choices=SUITES)
    parser.add_argument("--tasks", type=int, help="only the first N user tasks")
    parser.add_argument("--goals", type=int, help="only the first N attacker goals; 0 runs no attack")
    parser.add_argument("--reasoning-effort", default="none", help="none allows tool calls on chat completions")
    args = parser.parse_args()

    load_dotenv(".env")
    meter = Metered(openai.OpenAI(max_retries=5))
    agent = build_agent(OpenAILLM(meter, args.model, reasoning_effort=args.reasoning_effort))
    suite = get_suite(BENCHMARK_VERSION, args.suite)
    attack = Injection(suite, agent, spoken_name(args.model))
    task_ids = list(suite.user_tasks)[: args.tasks]
    injection_ids = list(suite.injection_tasks)[: args.goals]
    cases = [(task_id, None) for task_id in task_ids]
    cases += [(task_id, injection_id) for task_id in task_ids for injection_id in injection_ids]

    configuration = args.model if args.reasoning_effort == "none" else f"{args.model}-{args.reasoning_effort}"
    folder = RESULTS / configuration / args.suite
    records, failed, in_a_row = [], 0, 0
    for task_id, injection_id in cases:
        for check in (False, True):
            path = folder / ("check" if check else "plain") / f"{task_id}__{injection_id or 'no_attack'}.json"
            if path.exists():
                records.append(json.loads(path.read_text()))
                continue
            try:
                record = run_case(args.suite, task_id, injection_id, agent, attack, check, meter)
            except Exception as error:
                failed, in_a_row = failed + 1, in_a_row + 1
                print(f"{task_id} {injection_id or '-'}: {type(error).__name__}: {error}")
                if in_a_row == 3:
                    raise SystemExit(
                        "Stopped after three failures in a row. Finished cases are kept; rerun to continue."
                    )
                continue
            in_a_row = 0
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(record, indent=1, default=lambda value: value.model_dump()))
            records.append(json.loads(path.read_text()))
            print(
                f"{task_id:<14}{injection_id or '-':<18}{'check' if check else 'plain':<7}"
                f"solved={int(record['solved'])} attacked={int(record['attacked'])} calls={record['calls']}"
            )
    show(records)
    if failed:
        print(f"{failed} cases did not finish; rerun to try them again.")


if __name__ == "__main__":
    main()
