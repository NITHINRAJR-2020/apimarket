import { FormEvent, useEffect, useRef, useState } from "react";
import { api, ApiError } from "../services/api";

type ChatMessage = { role: "user" | "assistant"; content: string };

const WELCOME: ChatMessage = {
  role: "assistant",
  content:
    "Hi, I'm the APIMarket assistant. Ask me anything about how escrow, " +
    "listings, agents, or payments work here.",
};

export default function ChatWidget() {
  const [open, setOpen] = useState(false);
  const [messages, setMessages] = useState<ChatMessage[]>([WELCOME]);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (open) {
      scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
    }
  }, [messages, open]);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    const text = input.trim();
    if (!text || sending) return;

    const nextMessages = [...messages, { role: "user", content: text } as ChatMessage];
    setMessages(nextMessages);
    setInput("");
    setError(null);
    setSending(true);

    try {
      const history = nextMessages.filter((m) => m !== WELCOME);
      const { reply } = await api.sendChatMessage(text, history.slice(0, -1));
      setMessages((prev) => [...prev, { role: "assistant", content: reply }]);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Couldn't reach the assistant. Try again.");
    } finally {
      setSending(false);
    }
  }

  if (!open) {
    return (
      <button
        onClick={() => setOpen(true)}
        className="fixed bottom-5 right-5 z-20 rounded-full border border-ink-line2 bg-ink-panel px-4 py-2.5 text-sm font-medium text-paper hover:bg-ink-panel2"
      >
        Ask a question
      </button>
    );
  }

  return (
    <div className="fixed bottom-5 right-5 z-20 flex h-[28rem] w-80 flex-col rounded-lg border border-ink-line bg-ink-panel sm:w-96">
      <div className="flex items-center justify-between border-b border-ink-line px-4 py-3">
        <div>
          <div className="text-sm font-semibold text-paper">APIMarket assistant</div>
          <div className="text-xs text-paper-dim">Ask about listings, escrow, agents</div>
        </div>
        <button
          onClick={() => setOpen(false)}
          className="text-xs text-paper-dim hover:text-paper"
          aria-label="Close chat"
        >
          Close
        </button>
      </div>

      <div ref={scrollRef} className="flex-1 space-y-3 overflow-y-auto px-4 py-3">
        {messages.map((m, i) => (
          <div
            key={i}
            className={`max-w-[85%] rounded-md px-3 py-2 text-sm leading-relaxed ${
              m.role === "user"
                ? "ml-auto bg-brass/10 text-paper"
                : "mr-auto bg-ink-panel2 text-paper"
            }`}
          >
            {m.content}
          </div>
        ))}
        {sending && <div className="mr-auto text-xs text-paper-dim">Thinking…</div>}
        {error && <div className="mr-auto text-xs text-vault-red">{error}</div>}
      </div>

      <form onSubmit={handleSubmit} className="flex gap-2 border-t border-ink-line p-3">
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Type a question..."
          className="flex-1 rounded-md border border-ink-line2 bg-ink-bg px-3 py-2 text-sm text-paper placeholder:text-paper-dim focus:outline-none focus:ring-1 focus:ring-brass"
        />
        <button
          type="submit"
          disabled={sending || !input.trim()}
          className="rounded-md border border-ink-line2 bg-ink-panel2 px-3 py-2 text-sm font-medium text-paper hover:bg-ink-line disabled:opacity-50"
        >
          Send
        </button>
      </form>
    </div>
  );
}
