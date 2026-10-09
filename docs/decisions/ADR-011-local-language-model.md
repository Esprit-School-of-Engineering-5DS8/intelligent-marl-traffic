# ADR-011: A local language model for questions and demo scenarios

- Status: accepted
- Date: 2026-10-09

## Context

Operators and the jury should be able to query the results and set up a demonstration
in plain French ("Quel contrôleur gère le mieux l'accident sur le quartier ?", "Montre MP
contre COOP-FULL à Tunis avec des piétons") without knowing file names or command options.
Constraints:

- free, with no account, key or quota, and usable offline during the defence;
- the reported results must not change, and the assistant must never state a number that
  is not in our result files;
- it runs on the team's laptop: 4-core CPU, 12 GB of memory, no GPU large enough to help;
- it must still work when the model is absent, slow or wrong.

## Decision

- **Model:** Ollama serves `qwen2.5:3b` (about 2 GB) on the laptop; the code talks to its
  HTTP API with the standard library only (`src/cotraffic/assistant/llm.py`), so the
  project gains no dependency. Model and address can be changed with
  `COTRAFFIC_LLM_MODEL` and `COTRAFFIC_LLM_URL`.
- **The code answers, the model writes.** A question becomes a structured query (intent,
  network, scenario, demand, measure, methods) by keyword matching; the answer is looked up
  by code in the result files; the model phrases it from the facts it is given.
- **The model reads only what keywords cannot.** On a fixed test set keywords read 14 of 15
  questions correctly and the model alone 5, because it fills fields the question does not
  mention (journal, 2026-10-09). When the keywords cannot classify a question, the model
  reads it into JSON constrained to the values present in `results/summary/summary.csv`;
  a field the user named once still comes from the keywords, and a network or demand level
  the question does not mention is left to the defaults. Invalid JSON is retried once with
  the reason, then the keyword reading is used.
- **Number guard.** The model's text is kept only if every number in it - digits or words -
  is one of the facts, rounded as written, with the sign kept for interval bounds;
  otherwise the sentence written by code is shown.
- **Demo requests** are read the same way (keywords first) into the options of
  `scripts/demo_side_by_side.py`, then checked against what exists (trained checkpoints,
  networks with sidewalks) and corrected with a note, so the command always runs.
- **Not in the control loop.** Signals stay under the learned policies and the shield.

## Alternatives considered

- Hosted models (paid API): best quality, but a key, a cost per question and an internet
  connection at the defence.
- Free tiers of hosted APIs: quotas and outages make the demo fail unpredictably, and the
  questions leave the machine.
- A language model choosing phases during rare events: a decision every 5 s per junction
  against several seconds per answer on this laptop, non-reproducible runs, and it would be
  a new method to evaluate under the full protocol. Future work.
- A 7-billion-parameter local model: better phrasing, about 2-3 times slower on this CPU;
  `COTRAFFIC_LLM_MODEL=qwen2.5:7b` switches to it without code changes.

## Consequences

- The assistant answers only what the result files contain; anything else gets a message
  saying what exists.
- Without Ollama, `ask` and `demo-plan` still work (keyword reading, answers written by
  code); the smoke check covers that path.
- Speed and reading accuracy on the laptop are measured with `scripts/check_assistant.py`
  (journal, 2026-10-09).
