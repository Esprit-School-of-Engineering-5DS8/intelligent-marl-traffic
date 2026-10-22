import { ChatEvent, type PageContext } from "@/shared/schemas";

/**
 * Streams the backend's answer (Server-Sent Events over a POST). Each event is validated;
 * an invalid one is dropped, and nothing received is ever executed: tool calls are data
 * that the interface displays, and state-changing ones wait for the user's confirmation.
 */
export async function* streamChat(
  body: { question: string; context: PageContext; provider: string; language: string },
  signal: AbortSignal,
): AsyncGenerator<ChatEvent> {
  const response = await fetch("/api/assistant/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "text/event-stream" },
    body: JSON.stringify(body),
    signal,
  });
  if (!response.ok || !response.body) {
    yield { type: "error", message: `HTTP ${response.status}` };
    return;
  }
  const reader = response.body.pipeThrough(new TextDecoderStream()).getReader();
  let buffer = "";
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += value;
    let end: number;
    while ((end = buffer.indexOf("\n\n")) !== -1) {
      const chunk = buffer.slice(0, end);
      buffer = buffer.slice(end + 2);
      const data = chunk
        .split("\n")
        .filter((line) => line.startsWith("data:"))
        .map((line) => line.slice(5).trimStart())
        .join("\n");
      if (!data) continue;
      try {
        const parsed = ChatEvent.safeParse(JSON.parse(data));
        if (parsed.success) yield parsed.data;
      } catch {
        /* malformed event: ignored */
      }
    }
  }
}
