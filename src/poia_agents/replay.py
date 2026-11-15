"""Replays AgentDojo's reference solutions through the check, without an LLM."""

from collections import Counter

from agentdojo.agent_pipeline.ground_truth_pipeline import GroundTruthPipeline
from agentdojo.functions_runtime import FunctionsRuntime
from agentdojo.task_suite.load_suites import get_suite

from poia_agents.coverage import BENCHMARK_VERSION, SUITES
from poia_agents.guard import GuardedRuntime, Session

ROWS = ("tasks", "solved without the check", "solved with the check", "template", "fresh", "refused", "count left")


def replay_task(suite_name, task_id):
    suite = get_suite(BENCHMARK_VERSION, suite_name)
    task = suite.user_tasks[task_id]
    agent = GroundTruthPipeline(task)
    unguarded, _ = suite.run_task_with_pipeline(agent, task, None, {}, runtime_class=FunctionsRuntime)

    environment = suite.load_and_inject_default_environment({})
    reference = task.ground_truth(task.init_environment(environment.model_copy(deep=True)))
    session = Session(suite_name, task_id, reference, environment)
    guarded, _ = suite.run_task_with_pipeline(
        agent, task, None, {}, runtime_class=lambda tools: GuardedRuntime(tools, session), environment=environment
    )
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


def replay():
    result = {}
    for suite_name in SUITES:
        totals = Counter()
        for task_id in get_suite(BENCHMARK_VERSION, suite_name).user_tasks:
            totals.update(replay_task(suite_name, task_id))
        result[suite_name] = totals
    return result


def main():
    result = replay()
    print(f"{'':<26}" + "".join(f"{column:>11}" for column in [*SUITES, "all"]))
    for row in ROWS:
        cells = [result[suite][row] for suite in SUITES]
        print(f"{row:<26}" + "".join(f"{cell:>11}" for cell in [*cells, sum(cells)]))


if __name__ == "__main__":
    main()
