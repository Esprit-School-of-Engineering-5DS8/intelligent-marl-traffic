# Provenance of the LLM team

The files of this package, `src/cotraffic/envs/ev.py`, `configs/agents/llm_team.yaml` and
`tests/test_llm_team_*.py` come from a teammate's branch of the team repository:

- repository: `Esprit-School-of-Engineering-5DS8/intelligent-marl-traffic`
- source: our teammate's work (base `integration` at `b908238`), received as an archive
  without git history, from our teammate
- copied on 2026-10-27, byte for byte except the line endings (CRLF to LF); SHA-256 below
  is the hash of the source file as received.

They are excluded from ruff (`pyproject.toml`) so that they stay identical to the source.

## What is not taken

- The hosted providers (`src/cotraffic/llm/providers.py`: OpenCode Go, Groq, Gemini). No
  data leaves the machine and no API key is used; the only model is local (qwen2.5:3b).
- The source's changes to our environment (`traffic_env.py`, `observations.py`): the three
  readings they added are computed by `controllers/team.py` at decision time instead.
- The API, the frontend and the experiment configs of the branch.

## Files

| File | Source SHA-256 | Status |
|---|---|---|
| `src/cotraffic/controllers/llm_team/__init__.py` | `f322f723bd88a771d457c25cc81b89f6bf658b39e9a2532262841204797c1a53` | verbatim |
| `src/cotraffic/controllers/llm_team/agent.py` | `768c49c6d422ca7969754191aa9f2b201a9f34256af4a96ce658ebad969ad082` | verbatim |
| `src/cotraffic/controllers/llm_team/arbiter.py` | `a6b0b5f8d89711a17ee855122ef7b415e4da1d3aadeaeeb1c2f9b3b23e11221e` | verbatim |
| `src/cotraffic/controllers/llm_team/blackboard.py` | `1e1cf9a47952c94ead918cbdd8b0808eeb18fa0fe636e3955f36445145571031` | verbatim |
| `src/cotraffic/controllers/llm_team/client.py` | `d275244b63b0b325e1fb45b99b3a0c064097949da068d51f8a1cae77782df940` | **modified** (1) |
| `src/cotraffic/controllers/llm_team/controller.py` | `84d2e93eac185b4c1d9ff57400fb617b7e0664da807cde1641847d4cf5e7a218` | **modified** (2) |
| `src/cotraffic/controllers/llm_team/detector.py` | `aa2bb38ef3eff080232e98ba038c51609af042d0941bc5f0ffb17cf74fee9f49` | verbatim |
| `src/cotraffic/controllers/llm_team/directive_layer.py` | `837dffa451788ea94fe8c39d4c536317d7a4fd790620c3c71963fe58ad47f016` | verbatim |
| `src/cotraffic/controllers/llm_team/prompts/emergency.md` | `b7d681e72d5e6e1d990d376c9720000dead968d8a3ecaba6b86291cc1361fb7c` | verbatim |
| `src/cotraffic/controllers/llm_team/prompts/operator.md` | `b232d46775e26ffcbc3aa547c95203d4ec7e9e6b1ac51400d68107ff753a5a3c` | verbatim |
| `src/cotraffic/controllers/llm_team/prompts/pedestrian.md` | `f7f182755d840bcb5aa8853592edeee74663fc34415f08987f80749912fe91ab` | verbatim |
| `src/cotraffic/controllers/llm_team/roles/__init__.py` | `08598f418b2f024b30a18a1c61045fd572a1ad2433b566fde7066a6620b4ccfe` | verbatim |
| `src/cotraffic/controllers/llm_team/roles/emergency.py` | `336c879f22424dc69d49d378e453f88ad8158b3cb4616c86a5519d4635ab025d` | verbatim |
| `src/cotraffic/controllers/llm_team/roles/operator.py` | `8fe0569624663b26d7a984d0fd5cd3e04df18d903e31a832bcaebaab91825e38` | verbatim |
| `src/cotraffic/controllers/llm_team/roles/pedestrian.py` | `5d309f898b7d8a8b476661dd4a8e600ae71aed69b333d03f633776ffb2e9aeb8` | verbatim |
| `src/cotraffic/controllers/llm_team/schemas.py` | `516564aa522afc5ad84971afed5b8aaf8969c04ee6d76876b7b4b10f85391955` | verbatim |
| `src/cotraffic/controllers/llm_team/snapshot.py` | `fe0ce9ca99b19e1b565f49b39ddfe6008d9964dbdce248486eac94f3850a162f` | verbatim |
| `src/cotraffic/controllers/llm_team/supervisor.py` | `0c25fceea0d89786831fb2b5ae7aa4475574739200eb6fddd5f9de023ab1bd92` | verbatim |
| `src/cotraffic/envs/ev.py` | `fdc38585b4a3ce5c7ffe1e52e8e5f2ffb90068909df4f0e8c456228a5dfa9f9d` | verbatim |
| `configs/agents/llm_team.yaml` | `4c2d3ac65d31b0707a57d9a9ff1d73d43a839659204a5f55becf3db6e4b98bea` | verbatim |
| `tests/test_llm_team_arbiter.py` | `c59d040cc9b087a7026344cf31f8c00ada20a85c2abf31999d123b401aaaf7eb` | verbatim |
| `tests/test_llm_team_controller.py` | `c975e0f6c5ea662aee0de1b149ba01faf4fc4177f0b9e34190bc60bde4257804` | **modified** (3) |
| `tests/test_llm_team_directive_layer.py` | `ab481eef4195726728a91a967929543c6bd1b39e00b6f588bfffab5ff05597da` | verbatim |
| `tests/test_llm_team_roles.py` | `4ffb8d54c198d6c80aa23c29b3968a4aa68a91df40aa6a0e36c278a25dd95fd0` | verbatim |
| `tests/test_llm_team_schemas.py` | `ca703961f3ccc9dd6ba5b834705a77349982fd05b6c1cfeb370dd1ddeafa352e` | verbatim |
| `tests/test_llm_team_supervisor.py` | `6c6c6f5c71755e6be3d90a18f98b88b39cd978efc9c53b3a140fbf413c331964` | verbatim |

Modifications, each marked `CoTraffic:` in the file:

1. `client.py`: no import of the hosted providers; `_provider_client` raises
   `LLMUnavailableError` (no hosted model can be reached from this repository).
2. `controller.py`: one class attribute, `supervisor_class`, so that `team.py` plugs in the
   supervisor with the latency model.
3. `tests/test_llm_team_controller.py`: the registry test checks our names (`team_rules`,
   `team_qwen`) instead of `llm_team`.

## Ours (not from the branch)

- `src/cotraffic/controllers/team.py`: environment view, local client, latency model,
  `TeamController` (`team_rules`, `team_qwen`).
- `tests/test_team_integration.py`.
- `controllers/registry.py`: the `TEAM` methods.
