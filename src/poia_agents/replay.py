"""Replays AgentDojo's reference solutions and reference attacks through the check, without an LLM."""

from collections import Counter
from functools import cache

from agentdojo.agent_pipeline import AgentPipeline
from agentdojo.agent_pipeline.ground_truth_pipeline import GroundTruthPipeline
from agentdojo.base_tasks import BaseUserTask
from agentdojo.functions_runtime import FunctionsRuntime
from agentdojo.task_suite.load_suites import get_suite
from agentdojo.types import get_text_content_as_str

from poia_agents.coverage import BENCHMARK_VERSION, SUITES
from poia_agents.guard import GuardedRuntime, Session

TASK_ROWS = ("tasks", "solved without the check", "solved with the check", "template", "fresh", "refused", "count left")
ATTACK_ROWS = (
    "cases",
    "with a reference attack",
    "attack succeeds without the check",
    "attack succeeds with the check",
    "  inside a signed template",
    "  no state-changing operation",
    "injected operations",
    "  refused",
    "  allowed by a template",
    "user task solved without the check",
    "user task solved with the check",
)


@cache
def default_environment(suite_name):
    return get_suite(BENCHMARK_VERSION, suite_name).load_and_inject_default_environment({})


def start_of(suite_name, task):
    return task.init_environment(default_environment(suite_name).model_copy(deep=True))


def judge(task, output, before, after, trace):
    if isinstance(task, BaseUserTask):
        from_trace = task.utility_from_traces(output, before, after, trace)
        return task.utility(output, before, after) if from_trace is None else from_trace
    from_trace = task.security_from_traces(output, before, after, trace)
    return task.security(output, before, after) if from_trace is None else from_trace


def run(suite_name, task, agent, injection=None, session=None):
    suite = get_suite(BENCHMARK_VERSION, suite_name)
    environment = start_of(suite_name, task)
    before = environment.model_copy(deep=True)
    runtime = FunctionsRuntime(suite.tools) if session is None else GuardedRuntime(suite.tools, session)
    _, _, after, messages, _ = agent.query(task.PROMPT, runtime, environment)
    output = get_text_content_as_str(messages[-1]["content"] or [])
    trace = [call for message in messages if message["role"] == "assistant" for call in message["tool_calls"] or []]
    if session is not None:
        trace = session.executed(trace)
    solved = judge(task, output, before, after, trace)
    attacked = injection is not None and judge(injection, output, before, after, trace)
    return solved, attacked


def open_session(suite_name, task_id):
    task = get_suite(BENCHMARK_VERSION, suite_name).user_tasks[task_id]
    start = start_of(suite_name, task)
    return Session(suite_name, task_id, task.ground_truth(start), start)


def replay_task(suite_name, task_id):
    task = get_suite(BENCHMARK_VERSION, suite_name).user_tasks[task_id]
    agent = GroundTruthPipeline(task)
    unguarded, _ = run(suite_name, task, agent)
    session = open_session(suite_name, task_id)
    guarded, _ = run(suite_name, task, agent, session=session)
    outcomes = Counter(outcome for _, outcome in session.outcomes)
    return {
        "tasks": 1,
        "solved without the check": int(unguarded),
        "solved with the check": int(guarded),
        "template": outcomes["template"],
        "fresh": outcomes["fresh"],
        "refused": outcomes["refused"],
        "count left": sum(session.service.remaining.values()),
    }


def replay_attack(suite_name, task_id, injection_id):
    suite = get_suite(BENCHMARK_VERSION, suite_name)
    task, injection = suite.user_tasks[task_id], suite.injection_tasks[injection_id]
    agent = AgentPipeline([GroundTruthPipeline(injection), GroundTruthPipeline(task)])
    session = open_session(suite_name, task_id)
    reference = injection.ground_truth(session.environment)
    injected = [call for call in reference if call.function in session.write_tools]
    solved_unguarded, unguarded = run(suite_name, task, agent, injection)
    solved, guarded = run(suite_name, task, agent, injection, session)
    outcomes = Counter(outcome for _, outcome in session.outcomes[: len(injected)])
    return {
        "cases": 1,
        "with a reference attack": int(bool(reference)),
        "attack succeeds without the check": int(unguarded),
        "attack succeeds with the check": int(guarded),
        "  inside a signed template": int(guarded and outcomes["template"] > 0),
        "  no state-changing operation": int(guarded and not injected),
        "injected operations": len(injected),
        "  refused": outcomes["refused"],
        "  allowed by a template": outcomes["template"],
        "user task solved without the check": int(solved_unguarded),
        "user task solved with the check": int(solved),
    }


def replay(attacks=False):
    result = {}
    for suite_name in SUITES:
        suite = get_suite(BENCHMARK_VERSION, suite_name)
        totals = Counter()
        for task_id in suite.user_tasks:
            if attacks:
                for injection_id in suite.injection_tasks:
                    totals.update(replay_attack(suite_name, task_id, injection_id))
            else:
                totals.update(replay_task(suite_name, task_id))
        result[suite_name] = totals
    return result


def show(result, rows):
    print(f"{'':<36}" + "".join(f"{column:>11}" for column in [*SUITES, "all"]))
    for row in rows:
        cells = [result[suite][row] for suite in SUITES]
        print(f"{row:<36}" + "".join(f"{cell:>11}" for cell in [*cells, sum(cells)]))


def main():
    print("Reference solutions\n")
    show(replay(), TASK_ROWS)
    print("\nAn agent that obeys the injection completely\n")
    show(replay(attacks=True), ATTACK_ROWS)


if __name__ == "__main__":
    main()
