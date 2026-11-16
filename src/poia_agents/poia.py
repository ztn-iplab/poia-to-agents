"""Approvals through a PoIA relying party and ZT-Authenticator, verified here rather than taken on trust."""

import base64
import hashlib
import json
import math
import ssl
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from collections.abc import Mapping

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec

TEMPLATE_ACTION = "agent_template"
OPERATION_ACTION = "agent_operation"


def normalize(value):
    if isinstance(value, str):
        return unicodedata.normalize("NFC", value)
    if isinstance(value, bool) or value is None or isinstance(value, int):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("intent numbers must be finite")
        return int(value) if value.is_integer() else value
    if isinstance(value, list | tuple):
        return [normalize(item) for item in value]
    if isinstance(value, Mapping):
        return {unicodedata.normalize("NFC", key): normalize(child) for key, child in value.items()}
    raise TypeError(f"unsupported intent value type: {type(value).__name__}")


def canonical_json(data):
    return json.dumps(
        normalize(data), sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False
    ).encode()


def intent_hash(body):
    return base64.urlsafe_b64encode(hashlib.sha256(canonical_json(body)).digest()).decode("ascii")


def proof_hash(body, nonce, expires_at):
    payload = {"intent_hash": intent_hash(body), "nonce": nonce, "expires_at": int(expires_at)}
    return hashlib.sha256(canonical_json(payload)).hexdigest()


def approval_message(nonce, device_id, rp_id, digest):
    return f"{nonce}|{device_id}|{rp_id}|poia-approve:{digest}".encode()


def verify_p256(public_key, message, signature):
    try:
        key = serialization.load_der_public_key(base64.b64decode(public_key))
        if not isinstance(key, ec.EllipticCurvePublicKey):
            return False
        key.verify(base64.b64decode(signature), message, ec.ECDSA(hashes.SHA256()))
    except (ValueError, TypeError, InvalidSignature):
        return False
    return True


def unpadded(data):
    return base64.urlsafe_b64decode(data + "=" * (-len(data) % 4))


def passkey_approved(assertion, digest, origin):
    raw_client_data = unpadded(assertion["client_data_json"])
    client_data = json.loads(raw_client_data)
    if client_data.get("type") != "webauthn.get" or client_data.get("origin") != origin:
        return False
    if unpadded(client_data.get("challenge", "")) != bytes.fromhex(digest):
        return False
    authenticator_data = unpadded(assertion["authenticator_data"])
    host = urllib.parse.urlsplit(origin).hostname or ""
    if len(authenticator_data) < 37 or authenticator_data[:32] != hashlib.sha256(host.encode()).digest():
        return False
    if not authenticator_data[32] & 0x01:
        return False
    message = authenticator_data + hashlib.sha256(raw_client_data).digest()
    signature = base64.b64encode(unpadded(assertion["signature"])).decode()
    return any(verify_p256(key, message, signature) for key in assertion.get("public_keys", []))


def device_approved(record, digest, rp_id):
    return any(
        verify_p256(
            key["public_key"], approval_message(record["nonce"], key["device_id"], rp_id, digest), record["signature"]
        )
        for key in record.get("device_keys", [])
    )


def approved(record, action, scope, user_id, rp_id, origin="https://poia.local"):
    body = record.get("intent") or {}
    context = body.get("context") or {}
    if record.get("status") not in ("approved", "consumed") or body.get("action") != action:
        return False
    if canonical_json(body.get("scope") or {}) != canonical_json(scope):
        return False
    if context.get("user_id") != user_id or context.get("rp_id") != rp_id:
        return False
    digest = proof_hash(body, record["nonce"], record["expires_at"])
    if "webauthn" in record:
        return passkey_approved(record["webauthn"], digest, origin)
    return device_approved(record, digest, rp_id)


def operation_scope(tool, arguments, effect):
    return {"tool": tool, "targets": effect.targets, "amount": effect.amount, "arguments": arguments}


class RelyingParty:
    def __init__(self, url, user_id, rp_id, ca=None, transport=None, sleep=time.sleep, clock=time.time):
        self.url, self.user_id, self.rp_id = url.rstrip("/"), user_id, rp_id
        self.context = ssl.create_default_context(cafile=ca)
        self.transport = transport or self.http
        self.sleep, self.clock = sleep, clock

    def http(self, method, path, payload=None):
        data = None if payload is None else json.dumps(payload).encode()
        request = urllib.request.Request(self.url + path, data=data, method=method)
        request.add_header("Content-Type", "application/json")
        with urllib.request.urlopen(request, context=self.context, timeout=30) as response:
            return json.loads(response.read())

    def problem(self):
        try:
            self.transport("GET", "/api/poia/test/proof/preflight")
        except urllib.error.HTTPError as error:
            if error.code == 404:
                return None
            if error.code == 403:
                return f"{self.url} is running with POIA_TEST_MODE=false; set it to true and restart the prototype."
            return f"{self.url} answered HTTP {error.code}."
        except (urllib.error.URLError, OSError) as error:
            reason = getattr(error, "reason", error)
            return f"Cannot reach {self.url} ({reason}). Is the PoIA prototype running?"
        return None

    def approve(self, action, scope, created=lambda intent_id: None, poll=1.0):
        started = self.clock()
        context = {"user_id": self.user_id, "rp_id": self.rp_id}
        payload = {"action": action, "scope": scope, "context": context}
        intent_id = self.transport("POST", "/api/poia/test/intent", payload)["intent_id"]
        created(intent_id)
        while True:
            record = self.transport("GET", f"/api/poia/test/proof/{intent_id}")
            if record["status"] != "pending" or self.clock() > record["expires_at"]:
                break
            self.sleep(poll)
        ok = approved(record, action, scope, self.user_id, self.rp_id, self.url)
        return ok, record, self.clock() - started


class PoIAUser:
    def __init__(self, relying_party, signer="zt", notify=print, browser=webbrowser.open):
        self.relying_party = relying_party
        self.signer, self.notify, self.browser = signer, notify, browser
        self.log = []

    def created(self, intent_id):
        if self.signer == "webauthn":
            url = f"{self.relying_party.url}/poia/approve/{intent_id}"
            self.notify(f"  approve with your passkey at {url}")
            self.browser(url)
        else:
            self.notify("  approve in ZT-Authenticator on your phone")

    def ask(self, kind, name, action, scope):
        ok, record, seconds = self.relying_party.approve(action, scope, self.created)
        self.log.append(
            {"kind": kind, "name": name, "signer": self.signer, "approved": ok, "seconds": round(seconds, 2)}
        )
        self.notify(f"  {'approved' if ok else 'not approved'} after {seconds:.1f} s")
        return ok, record

    def sign(self, template):
        self.notify(f"Template '{template.kind}': {template.targets}, count {template.count}, limit {template.limit}")
        return self.ask("template", template.kind, TEMPLATE_ACTION, template.message())[1]

    def verify(self, template, record):
        party = self.relying_party
        return approved(record, TEMPLATE_ACTION, template.message(), party.user_id, party.rp_id, party.url)

    def approves(self, tool, arguments, effect):
        self.notify(f"Operation outside the templates: {tool} {effect.targets or arguments}")
        return self.ask("operation", tool, OPERATION_ACTION, operation_scope(tool, arguments, effect))[0]
