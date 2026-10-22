"""Natural-language access to the project: questions about the results and demo scenarios.

Keyword matching reads the request and code finds the answer in our result files; a small
language model running locally (Ollama) phrases it, and reads the requests keywords cannot
classify. Every step has a deterministic fallback, so the assistant still works when the
model is absent, slow or wrong.
"""
