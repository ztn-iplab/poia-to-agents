"""Each condition of the check refuses the operation it exists to refuse."""

from dataclasses import replace
from datetime import datetime

import pytest

from poia_agents.check import Effect, Request, Service, Template, new_key, public_key, sign
from poia_agents.coverage import load_catalog

NOW = datetime(2026, 11, 14, 12, 0)
FRIEND = "GB29NWBK60161331926819"
ATTACKER = "US133000000121212121212"


def interpret(tool, arguments):
    if tool == "send_money":
        return Effect({"payee": [arguments["recipient"]]}, arguments["amount"])
    return Effect()


@pytest.fixture
def user_key():
    return new_key()


@pytest.fixture
def agent_key():
    return new_key()


@pytest.fixture
def service(user_key):
    service = Service(load_catalog(), interpret)
    service.register_user("emma", public_key(user_key))
    return service


@pytest.fixture
def template(agent_key):
    return Template(
        template_id="t1",
        user="emma",
        agent_key=public_key(agent_key),
        kind="pay",
        targets={"payee": [FRIEND]},
        limit=50.0,
        count=2,
        expires="2026-12-01T00:00:00",
    )


@pytest.fixture
def stored(service, template, user_key):
    assert service.store_template(template, sign(user_key, template.message())).allowed
    return service


def payment(number="1", recipient=FRIEND, amount=10.0, template_id="t1"):
    return Request(template_id, number, "send_money", {"recipient": recipient, "amount": amount, "subject": "Refund"})


def ask(service, request, key, now=NOW):
    return service.authorize(request, sign(key, request.message()), now)


def test_operation_inside_the_template_is_allowed(stored, agent_key):
    assert ask(stored, payment(), agent_key).allowed


def test_c1_template_not_signed_by_the_user(service, template):
    assert service.store_template(template, sign(new_key(), template.message())).condition == "C1"
    assert service.templates == {}


def test_c1_template_changed_after_signing(service, template, user_key):
    signature = sign(user_key, template.message())
    wider = replace(template, limit=5000.0)
    assert service.store_template(wider, signature).condition == "C1"


def test_c1_template_stored_twice(stored, template, user_key):
    assert stored.store_template(template, sign(user_key, template.message())).condition == "C1"
    assert stored.remaining["t1"] == 2


def test_c2_request_signed_by_another_key(stored):
    assert ask(stored, payment(), new_key()).condition == "C2"


def test_c2_signature_reused_under_another_template(stored, template, user_key, agent_key):
    other = replace(template, template_id="t2", targets={"payee": [FRIEND, ATTACKER]})
    assert stored.store_template(other, sign(user_key, other.message())).allowed
    signature = sign(agent_key, payment().message())
    assert stored.authorize(payment(template_id="t2"), signature, NOW).condition == "C2"


def test_c3_operation_number_used_twice(stored, agent_key):
    assert ask(stored, payment(number="1"), agent_key).allowed
    assert ask(stored, payment(number="1"), agent_key).condition == "C3"


def test_c4_payee_not_named_in_the_template(stored, agent_key):
    assert ask(stored, payment(recipient=ATTACKER), agent_key).condition == "C4"


def test_c4_amount_over_the_limit(stored, agent_key):
    assert ask(stored, payment(amount=50.01), agent_key).condition == "C4"


def test_c4_template_expired(stored, agent_key):
    assert ask(stored, payment(), agent_key, now=datetime(2026, 12, 1)).condition == "C4"


def test_c4_tool_not_covered_by_the_template(stored, agent_key):
    request = Request("t1", "1", "send_email", {"recipients": ["mark.black-2134@gmail.com"]})
    assert ask(stored, request, agent_key).condition == "C4"


def test_c5_count_used_up(stored, agent_key):
    assert ask(stored, payment(number="1"), agent_key).allowed
    assert ask(stored, payment(number="2"), agent_key).allowed
    assert ask(stored, payment(number="3"), agent_key).condition == "C5"


def test_c6_operation_always_needs_a_fresh_approval(stored, agent_key):
    request = Request("t1", "1", "update_password", {"password": "new_password"})
    assert ask(stored, request, agent_key).condition == "C6"


def test_refused_operation_spends_nothing(stored, agent_key):
    assert not ask(stored, payment(recipient=ATTACKER), agent_key).allowed
    assert stored.remaining["t1"] == 2
    assert stored.used_numbers == set()


def test_stolen_agent_key_stays_inside_the_template(stored, agent_key):
    thief = agent_key
    assert ask(stored, payment(number="1", recipient=ATTACKER), thief).condition == "C4"
    assert ask(stored, payment(number="2", amount=5000.0), thief).condition == "C4"
    assert ask(stored, payment(number="3"), thief).allowed
    assert ask(stored, payment(number="4"), thief).allowed
    assert ask(stored, payment(number="5"), thief).condition == "C5"
