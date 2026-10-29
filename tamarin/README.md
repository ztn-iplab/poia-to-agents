# tamarin

Formal model of agent-mediated PoIA, built step by step alongside the code.

Roles: the User device (holds the signing key), the Agent (controlled by the attacker once it reads injected content), and the Tool server (the relying party that verifies before executing).

Main goal: every write the Tool server executes matches a commitment the User device made, with the same parameters and provenance.
