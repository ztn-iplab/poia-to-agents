"""The template labels agree with AgentDojo and reproduce the coverage reported in the paper."""

import pytest
from agentdojo.task_suite.load_suites import get_suite

from poia_agents.coverage import BENCHMARK_VERSION, SUITES, WRITE_TOOLS, coverage, load_catalog, load_labels

SOURCES = {"stated", "looked-up", "computed", "content"}

EXPECTED = {
    "banking": {"tasks": 16, "operations": 14, "inside_template": 7, "fresh": 7, "approvals": 14},
    "workspace": {"tasks": 40, "operations": 28, "inside_template": 18, "fresh": 10, "approvals": 28},
    "slack": {"tasks": 21, "operations": 34, "inside_template": 16, "fresh": 18, "approvals": 29},
    "travel": {"tasks": 20, "operations": 6, "inside_template": 6, "fresh": 0, "approvals": 6},
}

EXPECTED_CLASSES = {
    "banking": {"no state change": 4, "template only": 6, "template and fresh": 1, "fresh only": 5},
    "workspace": {"no state change": 18, "template only": 16, "template and fresh": 0, "fresh only": 6},
    "slack": {"no state change": 1, "template only": 8, "template and fresh": 2, "fresh only": 10},
    "travel": {"no state change": 14, "template only": 6, "template and fresh": 0, "fresh only": 0},
}


@pytest.mark.parametrize("suite_name", SUITES)
def test_labels_match_reference_solutions(suite_name):
    suite = get_suite(BENCHMARK_VERSION, suite_name)
    environment = suite.load_and_inject_default_environment({})
    labels = load_labels()[suite_name]
    assert set(labels) <= set(suite.user_tasks)
    for task_id, task in suite.user_tasks.items():
        reference = [
            call.function
            for call in task.ground_truth(environment.model_copy(deep=True))
            if call.function in WRITE_TOOLS[suite_name]
        ]
        labeled = [operation["tool"] for operation in labels.get(task_id, [])]
        assert labeled == reference, task_id


@pytest.mark.parametrize("suite_name", SUITES)
def test_stated_values_appear_in_the_request(suite_name):
    suite = get_suite(BENCHMARK_VERSION, suite_name)
    for task_id, operations in load_labels()[suite_name].items():
        request = suite.user_tasks[task_id].PROMPT.lower()
        for operation in operations:
            for target in operation["targets"]:
                if target["source"] == "stated":
                    assert target["value"].lower() in request, (task_id, target["value"])


def test_labels_use_the_catalog():
    catalog = load_catalog()
    tools_of = {template["id"]: set(template["tools"]) for template in catalog["templates"]}
    for suite_name, tasks in load_labels().items():
        for task_id, operations in tasks.items():
            for operation in operations:
                where = (suite_name, task_id, operation["tool"])
                assert operation["action"] in {"stated", "content"}, where
                assert all(target["source"] in SOURCES and target["role"] for target in operation["targets"]), where
                assert operation.get("amount", "stated") in SOURCES, where
                if operation["tool"] in catalog["always_fresh"]:
                    assert "template" not in operation, where
                else:
                    assert operation["tool"] in tools_of[operation["template"]], where


def test_coverage_matches_the_paper():
    result = coverage()
    for suite_name in SUITES:
        for key, value in EXPECTED[suite_name].items():
            assert result[suite_name][key] == value, (suite_name, key)
        for task_class, value in EXPECTED_CLASSES[suite_name].items():
            assert result[suite_name]["classes"][task_class] == value, (suite_name, task_class)
    assert sum(result[suite]["operations"] for suite in SUITES) == 82
    assert sum(result[suite]["inside_template"] for suite in SUITES) == 47
    assert sum(result[suite]["approvals"] for suite in SUITES) == 77
