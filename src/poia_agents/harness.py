"""Runs one AgentDojo case, with or without the check, and judges only what was executed."""

from functools import cache

from agentdojo.agent_pipeline import AbortAgentError
from agentdojo.base_tasks import BaseUserTask
from agentdojo.functions_runtime import FunctionsRuntime
from agentdojo.task_suite.load_suites import get_suite
from agentdojo.types import get_text_content_as_str

from poia_agents.coverage import BENCHMARK_VERSION
from poia_agents.guard import GuardedRuntime, Session


@cache
def default_environment(suite_name):
    return get_suite(BENCHMARK_VERSION, suite_name).load_and_inject_default_environment({})


def start_of(suite_name, task, injections=None):
    if injections:
        environment = get_suite(BENCHMARK_VERSION, suite_name).load_and_inject_default_environment(injections)
    else:
        environment = default_environment(suite_name).model_copy(deep=True)
    return task.init_environment(environment)


def open_session(suite_name, task_id, user=None, now=None):
    task = get_suite(BENCHMARK_VERSION, suite_name).user_tasks[task_id]
    start = start_of(suite_name, task)
    timing = {} if now is None else {"now": now}
    return Session(suite_name, task_id, task.ground_truth(start), start, user, **timing)


def judge(task, output, before, after, trace):
    if isinstance(task, BaseUserTask):
        from_trace = task.utility_from_traces(output, before, after, trace)
        return task.utility(output, before, after) if from_trace is None else from_trace
    from_trace = task.security_from_traces(output, before, after, trace)
    return task.security(output, before, after) if from_trace is None else from_trace


def answered(messages):
    return bool(messages) and messages[-1]["role"] == "assistant" and messages[-1]["content"] is not None


def run(suite_name, task, agent, injection=None, session=None, injections=None):
    suite = get_suite(BENCHMARK_VERSION, suite_name)
    environment = start_of(suite_name, task, injections)
    before = environment.model_copy(deep=True)
    runtime = FunctionsRuntime(suite.tools) if session is None else GuardedRuntime(suite.tools, session)
    messages = []
    for _ in range(3):
        try:
            _, _, environment, messages, _ = agent.query(task.PROMPT, runtime, environment)
        except AbortAgentError as error:
            environment, messages = error.task_environment, error.messages
        if answered(messages):
            break
    output = get_text_content_as_str(messages[-1]["content"]) if answered(messages) else ""
    trace = [call for message in messages if message["role"] == "assistant" for call in message["tool_calls"] or []]
    if session is not None:
        trace = session.executed(trace)
    solved = judge(task, output, before, environment, trace)
    attacked = injection is not None and judge(injection, output, before, environment, trace)
    return solved, attacked, messages
