"""Smoke test: the project installs, imports, and sees the pinned AgentDojo benchmark."""

from importlib.metadata import version

from agentdojo.task_suite.load_suites import get_suite

import poia_agents


def test_package_imports():
    assert poia_agents.__doc__


def test_agentdojo_is_pinned_version():
    assert version("agentdojo") == "0.1.35"


def test_banking_suite_loads():
    suite = get_suite("v1.2.2", "banking")
    assert len(suite.user_tasks) == 16
    assert len(suite.injection_tasks) == 9
