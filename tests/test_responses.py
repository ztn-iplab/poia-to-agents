"""Reasoning models run through the Responses API: tool calls, reasoning kept between turns, and the check."""

import json
from types import SimpleNamespace

from agentdojo.task_suite.load_suites import get_suite
from test_experiment import theft

from poia_agents import experiment
from poia_agents.coverage import BENCHMARK_VERSION
from poia_agents.experiment import Metered, build_agent, make_attack, run_case
from poia_agents.harness import start_of
from poia_agents.responses import ResponsesLLM

SUITE = get_suite(BENCHMARK_VERSION, "banking")


def refund():
    task = SUITE.user_tasks["user_task_3"]
    return task.ground_truth(start_of("banking", task))


class FakeResponses:
    def __init__(self, calls):
        self.calls, self.requests = list(calls), []
        self.responses = SimpleNamespace(create=self.create)
        self.models = SimpleNamespace(retrieve=lambda model: SimpleNamespace(id=model))

    def create(self, **request):
        self.requests.append(request)
        turn = len(self.requests)
        reasoning = SimpleNamespace(type="reasoning", id=f"rs_{turn}", summary=[], encrypted_content=f"secret-{turn}")
        if self.calls:
            call = self.calls.pop(0)
            arguments = json.dumps(dict(call.args))
            item = SimpleNamespace(
                type="function_call", call_id=f"call_{turn}", name=call.function, arguments=arguments
            )
        else:
            part = SimpleNamespace(type="output_text", text="Done.")
            item = SimpleNamespace(type="message", content=[part])
        usage = SimpleNamespace(
            input_tokens=1000, input_tokens_details=SimpleNamespace(cached_tokens=900), output_tokens=50
        )
        return SimpleNamespace(output=[reasoning, item], usage=usage)


def test_reasoning_agent_runs_a_case_under_the_check():
    api = FakeResponses([theft(), *refund()])
    meter = Metered(api)
    agent = build_agent(ResponsesLLM(meter, "gpt-6.1-sol", "low"))
    attack = make_attack("important_instructions", SUITE, agent, "GPT-6.1")
    record = run_case("banking", "user_task_3", "injection_task_5", agent, attack, True, meter)
    assert record["solved"] and not record["attacked"]
    assert record["outcomes"] == [("send_money", "refused"), ("send_money", "template")]
    assert (record["calls"], record["input_tokens"], record["cached_tokens"], record["output_tokens"]) == (
        4,
        4000,
        3600,
        200,
    )


def test_requests_carry_reasoning_settings_and_tools_in_responses_form():
    api = FakeResponses([theft()])
    agent = build_agent(ResponsesLLM(Metered(api), "gpt-6.1-sol", "low"))
    run_case("banking", "user_task_3", None, agent, None, True)
    first = api.requests[0]
    assert first["model"] == "gpt-6.1-sol" and first["reasoning"] == {"effort": "low"}
    assert first["include"] == ["reasoning.encrypted_content"] and first["store"] is False
    send_money = next(tool for tool in first["tools"] if tool["name"] == "send_money")
    assert send_money["type"] == "function" and "recipient" in send_money["parameters"]["properties"]
    assert [item.get("role") for item in first["input"]] == ["developer", "user"]


def test_reasoning_and_tool_results_are_sent_back_on_the_next_turn():
    api = FakeResponses([theft()])
    agent = build_agent(ResponsesLLM(Metered(api), "gpt-6.1-sol", "low"))
    run_case("banking", "user_task_3", None, agent, None, True)
    second = api.requests[1]["input"]
    reasoning = next(item for item in second if item.get("type") == "reasoning")
    call = next(item for item in second if item.get("type") == "function_call")
    result = next(item for item in second if item.get("type") == "function_call_output")
    assert reasoning == {"type": "reasoning", "id": "rs_1", "summary": [], "encrypted_content": "secret-1"}
    assert call["call_id"] == result["call_id"] == "call_1"
    assert "outside the user's approval" in result["output"]


def test_command_runs_a_reasoning_model_in_its_own_folder(monkeypatch, tmp_path):
    api = FakeResponses([])
    monkeypatch.setattr(experiment.openai, "OpenAI", lambda **_: api)
    monkeypatch.setattr(experiment, "RESULTS", tmp_path)
    arguments = [
        "--model",
        "gpt-6.1-sol",
        "--api",
        "responses",
        "--reasoning-effort",
        "low",
        "--tasks",
        "1",
        "--goals",
        "0",
    ]
    monkeypatch.setattr("sys.argv", ["experiment", *arguments])
    experiment.main()
    saved = sorted(path.relative_to(tmp_path).as_posix() for path in tmp_path.rglob("*.json"))
    folder = "gpt-6.1-sol-responses-low/important_instructions/run1/banking"
    assert saved == [f"{folder}/check/user_task_0__no_attack.json", f"{folder}/plain/user_task_0__no_attack.json"]
    record = json.loads((tmp_path / saved[0]).read_text())
    assert (record["api"], record["reasoning_effort"]) == ("responses", "low")
    assert record["messages"][-1]["responses_output"][0]["encrypted_content"].startswith("secret-")
