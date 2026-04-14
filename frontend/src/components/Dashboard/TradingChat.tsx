import { useRef, useState } from "react";
import { sendChatMessage, type ChatAnnotation, type ChatResponseData } from "../../api/client";

const ASSETS = ["BTC/USDT", "ETH/USDT", "SOL/USDT"];
const TIMEFRAMES = ["1h", "4h", "1d"];

const QUICK_PROMPTS = [
  "Should I long or short right now?",
  "What are the key support and resistance levels?",
  "Analyze order blocks and fair value gaps",
  "What's the best entry with SL and TP?",
  "Is there a breakout setup forming?",
  "What does the volume profile suggest?",
  "Rate the current risk/reward for a long position",
];

interface ChatMessage {
  role: "user" | "assistant";
  content: string;
  annotations?: ChatAnnotation[];
  timestamp: Date;
}

interface TradingChatProps {
  onAnnotations?: (annotations: ChatAnnotation[]) => void;
}

export function TradingChat({ onAnnotations }: TradingChatProps) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [asset, setAsset] = useState("BTC/USDT");
  const [tf, setTf] = useState("4h");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);

  const sendMessage = async (text: string) => {
    if (!text.trim() || loading) return;

    const userMsg: ChatMessage = { role: "user", content: text, timestamp: new Date() };
    setMessages((prev) => [...prev, userMsg]);
    setInput("");
    setLoading(true);
    setError(null);

    try {
      const history = messages.map((m) => ({ role: m.role, content: m.content }));
      const resp: ChatResponseData = await sendChatMessage(text, asset, tf, history);

      const assistantMsg: ChatMessage = {
        role: "assistant",
        content: resp.message,
        annotations: resp.annotations,
        timestamp: new Date(),
      };
      setMessages((prev) => [...prev, assistantMsg]);

      // Send annotations to chart
      if (resp.annotations.length > 0 && onAnnotations) {
        onAnnotations(resp.annotations);
      }

      // Scroll to bottom
      setTimeout(() => scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" }), 100);
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : "Chat failed";
      // Check for 503 (API key not configured)
      if (msg.includes("503") || msg.includes("ANTHROPIC_API_KEY")) {
        setError("Add your ANTHROPIC_API_KEY to .env file to enable AI chat");
      } else {
        setError(msg);
      }
    } finally {
      setLoading(false);
    }
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    void sendMessage(input);
  };

  return (
    <div className="rounded-lg border border-border bg-surface">
      {/* Header */}
      <div className="flex items-center justify-between border-b border-border px-4 py-3">
        <div className="flex items-center gap-2">
          <svg className="h-5 w-5 text-accent" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 10h.01M12 10h.01M16 10h.01M9 16H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-5l-5 5v-5z" />
          </svg>
          <h2 className="text-sm font-semibold text-white">AI Trading Assistant</h2>
        </div>
        <div className="flex items-center gap-2">
          <select value={asset} onChange={(e) => setAsset(e.target.value)}
            className="rounded border border-border bg-background px-2 py-1 text-xs text-white" aria-label="Chat asset">
            {ASSETS.map((a) => <option key={a} value={a}>{a}</option>)}
          </select>
          <select value={tf} onChange={(e) => setTf(e.target.value)}
            className="rounded border border-border bg-background px-2 py-1 text-xs text-white" aria-label="Chat timeframe">
            {TIMEFRAMES.map((t) => <option key={t} value={t}>{t.toUpperCase()}</option>)}
          </select>
        </div>
      </div>

      {/* Messages */}
      <div ref={scrollRef} className="h-[400px] overflow-y-auto px-4 py-3 space-y-3">
        {messages.length === 0 && (
          <div className="space-y-3">
            <p className="text-sm text-gray-400">
              Ask me about market analysis, entry points, or trading strategies.
              I analyze live data including order blocks, fair value gaps, volume, and technical indicators.
            </p>
            <div className="space-y-1.5">
              <p className="text-xs text-gray-500 uppercase tracking-wide">Quick prompts:</p>
              {QUICK_PROMPTS.map((prompt) => (
                <button key={prompt} type="button" onClick={() => void sendMessage(prompt)}
                  className="block w-full rounded border border-border bg-background px-3 py-2 text-left text-xs text-gray-300 hover:border-accent hover:text-white transition-colors"
                  aria-label={prompt}>
                  {prompt}
                </button>
              ))}
            </div>
          </div>
        )}

        {messages.map((msg, i) => (
          <div key={i} className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"}`}>
            <div className={`max-w-[85%] rounded-lg px-3 py-2 text-sm ${
              msg.role === "user"
                ? "bg-accent text-white"
                : "bg-background text-gray-200"
            }`}>
              {msg.role === "assistant" ? (
                <FormattedMessage text={msg.content} />
              ) : (
                <p>{msg.content}</p>
              )}

              {/* Annotation badges */}
              {msg.annotations && msg.annotations.length > 0 && (
                <div className="mt-2 flex flex-wrap gap-1">
                  {msg.annotations.map((a, j) => (
                    <span key={j} className={`rounded px-2 py-0.5 text-xs font-mono ${
                      a.type === "entry" ? "bg-accent/20 text-accent" :
                      a.type === "stop_loss" ? "bg-bearish/20 text-bearish" :
                      "bg-bullish/20 text-bullish"
                    }`}>
                      {a.label}: ${a.price.toLocaleString()}
                    </span>
                  ))}
                </div>
              )}

              <span className="mt-1 block text-xs opacity-50">
                {msg.timestamp.toLocaleTimeString()}
              </span>
            </div>
          </div>
        ))}

        {loading && (
          <div className="flex justify-start">
            <div className="rounded-lg bg-background px-4 py-3">
              <div className="flex items-center gap-2 text-sm text-gray-400">
                <svg className="h-4 w-4 animate-spin" viewBox="0 0 24 24" fill="none">
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                </svg>
                Analyzing {asset} {tf}...
              </div>
            </div>
          </div>
        )}

        {error && (
          <div className="rounded border border-bearish/30 bg-bearish/10 px-3 py-2 text-sm text-bearish">
            {error}
          </div>
        )}
      </div>

      {/* Input */}
      <form onSubmit={handleSubmit} className="border-t border-border px-4 py-3">
        <div className="flex gap-2">
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder={`Ask about ${asset}...`}
            className="flex-1 rounded border border-border bg-background px-3 py-2 text-sm text-white placeholder-gray-500 focus:border-accent focus:outline-none"
            disabled={loading}
            aria-label="Chat message input"
          />
          <button type="submit" disabled={loading || !input.trim()}
            className="rounded bg-accent px-4 py-2 text-sm font-medium text-white hover:bg-accent/80 disabled:opacity-40"
            aria-label="Send message">
            Send
          </button>
        </div>
      </form>
    </div>
  );
}

/** Format assistant messages with basic markdown-like rendering */
function FormattedMessage({ text }: { text: string }) {
  // Remove the JSON annotation block from displayed text
  const cleaned = text.replace(/```json\s*\{[\s\S]*?"annotations"[\s\S]*?\}\s*```/g, "").trim();

  const lines = cleaned.split("\n");
  return (
    <div className="space-y-1">
      {lines.map((line, i) => {
        if (line.startsWith("###")) return <h4 key={i} className="font-semibold text-white mt-2">{line.replace(/^###\s*/, "")}</h4>;
        if (line.startsWith("##")) return <h3 key={i} className="font-bold text-white mt-2">{line.replace(/^##\s*/, "")}</h3>;
        if (line.startsWith("**") && line.endsWith("**")) return <p key={i} className="font-semibold text-white">{line.replace(/\*\*/g, "")}</p>;
        if (line.startsWith("- ") || line.startsWith("• ")) return <p key={i} className="pl-3 text-gray-300">{line}</p>;
        if (line.startsWith("```")) return null;
        if (line.trim() === "") return <br key={i} />;
        return <p key={i}>{line}</p>;
      })}
    </div>
  );
}
