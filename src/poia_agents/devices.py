"""Software stand-ins for ZT-Authenticator and a passkey, producing the records the PoIA prototype keeps."""

import base64
import hashlib
import json

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec

from poia_agents.poia import approval_message, proof_hash


def websafe(data):
    return base64.urlsafe_b64encode(data).decode().rstrip("=")


def der(key):
    encoded = key.public_key().public_bytes(serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)
    return base64.b64encode(encoded).decode()


def pending(action, scope, user_id, rp_id, intent_id="intent-1"):
    body = {"action": action, "scope": scope, "context": {"user_id": user_id, "rp_id": rp_id}}
    return {
        "status": "pending",
        "intent": body,
        "nonce": f"nonce-{intent_id}",
        "expires_at": 1_900_000_000,
        "signature": "",
        "device_keys": [],
    }


class Phone:
    def __init__(self, decide=lambda body: True, device_id=91, rp_id="poia-demo-bank"):
        self.key = ec.generate_private_key(ec.SECP256R1())
        self.device_id, self.rp_id, self.decide, self.shown = device_id, rp_id, decide, []
        self.public_key = der(self.key)

    def device_keys(self):
        return [{"device_id": self.device_id, "public_key": self.public_key}]

    def approve(self, record):
        digest = proof_hash(record["intent"], record["nonce"], record["expires_at"])
        message = approval_message(record["nonce"], self.device_id, self.rp_id, digest)
        signature = base64.b64encode(self.key.sign(message, ec.ECDSA(hashes.SHA256()))).decode()
        return {"status": "approved", "signature": signature}


class Passkey:
    def __init__(self, decide=lambda body: True, origin="https://poia.local", host="poia.local", flags=0x05):
        self.key = ec.generate_private_key(ec.SECP256R1())
        self.decide, self.origin, self.host, self.flags, self.shown = decide, origin, host, flags, []
        self.public_key = der(self.key)

    def device_keys(self):
        return []

    def approve(self, record):
        digest = proof_hash(record["intent"], record["nonce"], record["expires_at"])
        client_data = json.dumps(
            {"type": "webauthn.get", "challenge": websafe(bytes.fromhex(digest)), "origin": self.origin}
        ).encode()
        authenticator_data = hashlib.sha256(self.host.encode()).digest() + bytes([self.flags]) + (7).to_bytes(4, "big")
        signed = authenticator_data + hashlib.sha256(client_data).digest()
        signature = websafe(self.key.sign(signed, ec.ECDSA(hashes.SHA256())))
        assertion = {
            "authenticator_data": websafe(authenticator_data),
            "client_data_json": websafe(client_data),
            "signature": signature,
            "public_keys": [self.public_key],
        }
        return {"status": "consumed", "signature": signature, "webauthn": assertion}


def signed(device, action, scope, user_id, rp_id):
    record = pending(action, scope, user_id, rp_id)
    record["device_keys"] = device.device_keys()
    record.update(device.approve(record))
    return record
