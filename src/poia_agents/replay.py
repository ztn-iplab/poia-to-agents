"""Replays AgentDojo's reference solutions and reference attacks through the check, without an LLM."""

from collections import Counter

from agentdojo.agent_pipeline import AgentPipeline, GroundTruthPipeline
from agentdojo.task_suite.load_suites import get_suite

from poia_agents.coverage import BENCHMARK_VERSION, SUITES
from poia_agents.harness import open_session, run

TASK_ROWS = ("tasks", "solved without the check", "solved with the check", "template", "fresh", "refused", "count left")
ATTACK_ROWS = (
    "cases",
    "with a reference attack",
    "attack succeeds without the check",
    "attack succeeds with the check",
    "  inside a signed template",
    "  through a fresh approval",
    "  no state-changing operation",
    "injected operations",
    "  refused",
    "  allowed by a template",
    "  approved by the user",
    "user task solved without the check",
    "user task solved with the check",
)


def replay_task(suite_name, task_id):
    task = get_suite(BENCHMARK_VERSION, suite_name).user_tasks[task_id]
    agent = GroundTruthPipeline(task)
    unguarded, _, _ = run(suite_name, task, agent)
    session = open_session(suite_name, task_id)
    guarded, _, _ = run(suite_name, task, agent, session=session)
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
    solved_unguarded, unguarded, _ = run(suite_name, task, agent, injection)
    solved, guarded, _ = run(suite_name, task, agent, injection, session)
    outcomes = Counter(outcome for _, outcome in session.outcomes[: len(injected)])
    return {
        "cases": 1,
        "with a reference attack": int(bool(reference)),
        "attack succeeds without the check": int(unguarded),
        "attack succeeds with the check": int(guarded),
        "  inside a signed template": int(guarded and outcomes["template"] > 0),
        "  through a fresh approval": int(guarded and outcomes["fresh"] > 0 and not outcomes["template"]),
        "  no state-changing operation": int(guarded and not injected),
        "injected operations": len(injected),
        "  refused": outcomes["refused"],
        "  allowed by a template": outcomes["template"],
        "  approved by the user": outcomes["fresh"],
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
