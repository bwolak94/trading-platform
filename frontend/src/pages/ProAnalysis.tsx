import { useState, useRef, useEffect, useCallback } from "react";
import { sendProAnalysis } from "../api/client";
import type { ProAnalysisData } from "../api/client";

/* ------------------------------------------------------------------ */
/*  Constants                                                         */
/* ------------------------------------------------------------------ */

const ASSETS = [
  "BTC/USDT", "ETH/USDT", "SOL/USDT", "BNB/USDT", "XRP/USDT",
  "DOGE/USDT", "ADA/USDT", "AVAX/USDT", "DOT/USDT", "LINK/USDT",
  "EUR/USD", "GBP/USD", "XAU/USD", "GBP/JPY",
] as const;

const TIMEFRAMES = [
  { value: "5m", label: "5m" },
  { value: "15m", label: "15m" },
  { value: "1h", label: "1H" },
  { value: "4h", label: "4H" },
  { value: "1d", label: "1D" },
  { value: "1w", label: "1W" },
] as const;

const QUICK_PROMPTS = [
  "Full technical analysis",
  "Should I go long or short?",
  "What are the key support/resistance levels?",
  "Calculate probability of breakout",
  "Analyze this chart",
  "What does the order flow suggest?",
] as const;

const MAX_IMAGE_SIZE = 5 * 1024 * 1024; // 5 MB

/* ------------------------------------------------------------------ */
/*  Types                                                             */
/* ------------------------------------------------------------------ */

interface ChatMessage {
  role: "user" | "assistant";
  content: string;
  imagePreview?: string;
  marketData?: ProAnalysisData;
}

/* ------------------------------------------------------------------ */
/*  Markdown renderer                                                 */
/* ------------------------------------------------------------------ */

function renderMarkdown(text: string): string {
  let html = text;

  // Code blocks (```lang ... ```)
  html = html.replace(/```(\w*)\n([\s\S]*?)```/g, (_match, lang: string, code: string) => {
    const escaped = code
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;");
    return `<pre class="bg-gray-900 rounded p-3 my-2 overflow-x-auto text-sm"><code class="language-${lang}">${escaped}</code></pre>`;
  });

  // Inline code
  html = html.replace(/`([^`]+)`/g, '<code class="bg-gray-800 px-1 rounded text-yellow-300 text-sm">$1</code>');

  // Tables
  html = html.replace(
    /((?:\|.*\|\r?\n)+)/g,
    (_match, tableBlock: string) => {
      const rows = tableBlock.trim().split("\n").filter((r) => r.trim());
      if (rows.length < 2) return tableBlock;

      let table = '<table class="w-full my-3 text-sm border-collapse">';
      rows.forEach((row, idx) => {
        // Skip separator row (| --- | --- |)
        if (/^\|[\s\-:|]+\|$/.test(row.trim())) return;
        const cells = row
          .split("|")
          .filter((c) => c.trim() !== "")
          .map((c) => c.trim());
        const tag = idx === 0 ? "th" : "td";
        const cls =
          idx === 0
            ? 'class="border border-gray-700 px-3 py-1.5 bg-gray-800 text-left font-semibold text-gray-200"'
            : 'class="border border-gray-700 px-3 py-1.5 text-gray-300"';
        table += "<tr>" + cells.map((c) => `<${tag} ${cls}>${c}</${tag}>`).join("") + "</tr>";
      });
      table += "</table>";
      return table;
    },
  );

  // Headers
  html = html.replace(/^#### (.+)$/gm, '<h4 class="text-base font-bold text-white mt-4 mb-1">$1</h4>');
  html = html.replace(/^### (.+)$/gm, '<h3 class="text-lg font-bold text-white mt-4 mb-1">$1</h3>');
  html = html.replace(/^## (.+)$/gm, '<h2 class="text-xl font-bold text-blue-400 mt-5 mb-2">$1</h2>');
  html = html.replace(/^# (.+)$/gm, '<h1 class="text-2xl font-bold text-white mt-5 mb-2">$1</h1>');

  // Bold & italic
  html = html.replace(/\*\*\*(.+?)\*\*\*/g, "<strong><em>$1</em></strong>");
  html = html.replace(/\*\*(.+?)\*\*/g, '<strong class="text-white">$1</strong>');
  html = html.replace(/\*(.+?)\*/g, "<em>$1</em>");

  // Unordered lists
  html = html.replace(/^- (.+)$/gm, '<li class="ml-4 list-disc text-gray-300">$1</li>');

  // Wrap consecutive <li> elements in <ul>
  html = html.replace(/((?:<li[^>]*>.*<\/li>\n?)+)/g, '<ul class="my-2">$1</ul>');

  // Line breaks for remaining plain text
  html = html.replace(/\n/g, "<br />");

  // Clean up excessive <br /> after block elements
  html = html.replace(/(<\/(?:pre|table|ul|h[1-4])>)(?:<br \/>)+/g, "$1");
  html = html.replace(/(?:<br \/>)+(<(?:pre|table|ul|h[1-4]))/g, "$1");

  return html;
}

/* ------------------------------------------------------------------ */
/*  Sub-components                                                    */
/* ------------------------------------------------------------------ */

function ProbabilityGauge({ long, short }: { long: number; short: number }) {
  return (
    <div className="rounded-lg border border-gray-700 bg-gray-800 p-4" role="figure" aria-label="Probability gauge">
      <h3 className="mb-3 text-sm font-semibold text-gray-400 uppercase tracking-wide">Probability</h3>
      <div className="flex items-center justify-between mb-1 text-xs font-medium">
        <span className="text-green-400">LONG {long}%</span>
        <span className="text-red-400">SHORT {short}%</span>
      </div>
      <div className="h-4 w-full rounded-full bg-gray-700 overflow-hidden flex">
        <div
          className="h-full bg-gradient-to-r from-green-600 to-green-400 transition-all duration-500"
          style={{ width: `${long}%` }}
          role="meter"
          aria-valuenow={long}
          aria-valuemin={0}
          aria-valuemax={100}
          aria-label={`Long probability ${long}%`}
        />
        <div
          className="h-full bg-gradient-to-r from-red-400 to-red-600 transition-all duration-500"
          style={{ width: `${short}%` }}
          role="meter"
          aria-valuenow={short}
          aria-valuemin={0}
          aria-valuemax={100}
          aria-label={`Short probability ${short}%`}
        />
      </div>
    </div>
  );
}

function RecommendationCard({ rec }: { rec: NonNullable<ProAnalysisData["recommendation"]> }) {
  const isLong = rec.action === "LONG";
  return (
    <div
      className={`rounded-lg border p-4 ${isLong ? "border-green-700 bg-green-950/40" : "border-red-700 bg-red-950/40"}`}
      role="region"
      aria-label="Trade recommendation"
    >
      <div className="flex items-center justify-between mb-3">
        <span className={`text-lg font-bold ${isLong ? "text-green-400" : "text-red-400"}`}>
          {rec.action}
        </span>
        <span className="rounded bg-gray-700 px-2 py-0.5 text-xs text-gray-300">
          Confidence: {rec.confidence}%
        </span>
      </div>
      <div className="grid grid-cols-2 gap-2 text-sm">
        <div>
          <span className="text-gray-500">Entry</span>
          <p className="text-white font-mono">${rec.entry}</p>
        </div>
        <div>
          <span className="text-gray-500">Stop Loss</span>
          <p className="text-red-400 font-mono">${rec.stop_loss}</p>
        </div>
        <div>
          <span className="text-gray-500">TP1</span>
          <p className="text-green-400 font-mono">${rec.take_profit_1}</p>
        </div>
        <div>
          <span className="text-gray-500">TP2</span>
          <p className="text-green-400 font-mono">${rec.take_profit_2}</p>
        </div>
        <div>
          <span className="text-gray-500">TP3</span>
          <p className="text-green-400 font-mono">${rec.take_profit_3}</p>
        </div>
        <div>
          <span className="text-gray-500">R:R</span>
          <p className="text-yellow-400 font-mono">{rec.risk_reward}x</p>
        </div>
      </div>
      {rec.timeframe && (
        <p className="mt-2 text-xs text-gray-500">Timeframe: {rec.timeframe}</p>
      )}
    </div>
  );
}

function MarketDataPanel({ data }: { data: Record<string, unknown> }) {
  const indicators = data.indicators as Record<string, number> | undefined;
  const regime = data.regime as { regime?: string; confidence?: number } | undefined;
  const orderBlocks = data.order_blocks as {
    bullish?: { price: string; strength: number }[];
    bearish?: { price: string; strength: number }[];
  } | undefined;
  const fvg = data.fvg as {
    bullish_gaps?: number;
    bearish_gaps?: number;
    nearest?: { type: string; range: string }[];
  } | undefined;

  if (!indicators) return null;

  return (
    <div className="space-y-4">
      {/* Price & Regime */}
      <div className="rounded-lg border border-gray-700 bg-gray-800 p-4" role="region" aria-label="Market summary">
        <h3 className="mb-2 text-sm font-semibold text-gray-400 uppercase tracking-wide">Market Summary</h3>
        <div className="flex items-center justify-between mb-2">
          <span className="text-gray-400 text-sm">Price</span>
          <span className="text-white font-mono font-bold">${String(data.current_price ?? "")}</span>
        </div>
        {regime && (
          <div className="flex items-center justify-between mb-2">
            <span className="text-gray-400 text-sm">Regime</span>
            <span
              className={`rounded px-2 py-0.5 text-xs font-semibold ${
                regime.regime === "TREND_BULL"
                  ? "bg-green-900 text-green-300"
                  : regime.regime === "TREND_BEAR"
                    ? "bg-red-900 text-red-300"
                    : "bg-yellow-900 text-yellow-300"
              }`}
            >
              {regime.regime} ({regime.confidence ?? 0}%)
            </span>
          </div>
        )}
      </div>

      {/* Indicators */}
      <div className="rounded-lg border border-gray-700 bg-gray-800 p-4" role="region" aria-label="Technical indicators">
        <h3 className="mb-2 text-sm font-semibold text-gray-400 uppercase tracking-wide">Indicators</h3>
        <div className="space-y-1 text-sm">
          {((): [string, number | undefined, string][] => {
            const rsi = indicators.rsi_14;
            const adx = indicators.adx_14;
            const macd = indicators.macd;
            const emaCross = indicators.ema_cross_signal;
            const volRatio = indicators.volume_vs_avg;
            return [
              ["RSI(14)", rsi, rsi !== undefined && rsi > 70 ? "text-red-400" : rsi !== undefined && rsi < 30 ? "text-green-400" : "text-gray-300"],
              ["ADX(14)", adx, adx !== undefined && adx > 25 ? "text-yellow-400" : "text-gray-300"],
              ["MACD", macd, macd !== undefined && macd > 0 ? "text-green-400" : "text-red-400"],
              ["EMA Cross", emaCross, emaCross !== undefined && emaCross > 0 ? "text-green-400" : emaCross !== undefined && emaCross < 0 ? "text-red-400" : "text-gray-300"],
              ["BB Pos", indicators.bb_position, "text-gray-300"],
              ["Vol Ratio", volRatio, volRatio !== undefined && volRatio > 1.5 ? "text-yellow-400" : "text-gray-300"],
              ["ATR%", indicators.atr_pct, "text-gray-300"],
            ];
          })().map(([label, val, cls]) => (
            <div key={label} className="flex items-center justify-between">
              <span className="text-gray-500">{label}</span>
              <span className={`font-mono ${cls}`}>{val ?? "-"}</span>
            </div>
          ))}
        </div>
      </div>

      {/* Order Blocks */}
      {orderBlocks && (
        <div className="rounded-lg border border-gray-700 bg-gray-800 p-4" role="region" aria-label="Order blocks">
          <h3 className="mb-2 text-sm font-semibold text-gray-400 uppercase tracking-wide">Order Blocks</h3>
          {orderBlocks.bullish && orderBlocks.bullish.length > 0 && (
            <div className="mb-2">
              <span className="text-xs text-green-500 font-semibold">DEMAND</span>
              {orderBlocks.bullish.map((ob, i) => (
                <div key={`bull-${i}`} className="flex justify-between text-xs mt-1">
                  <span className="text-gray-400 font-mono">{ob.price}</span>
                  <span className="text-green-400">str: {ob.strength.toFixed(1)}</span>
                </div>
              ))}
            </div>
          )}
          {orderBlocks.bearish && orderBlocks.bearish.length > 0 && (
            <div>
              <span className="text-xs text-red-500 font-semibold">SUPPLY</span>
              {orderBlocks.bearish.map((ob, i) => (
                <div key={`bear-${i}`} className="flex justify-between text-xs mt-1">
                  <span className="text-gray-400 font-mono">{ob.price}</span>
                  <span className="text-red-400">str: {ob.strength.toFixed(1)}</span>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* FVG */}
      {fvg && (fvg.bullish_gaps ?? 0) + (fvg.bearish_gaps ?? 0) > 0 && (
        <div className="rounded-lg border border-gray-700 bg-gray-800 p-4" role="region" aria-label="Fair value gaps">
          <h3 className="mb-2 text-sm font-semibold text-gray-400 uppercase tracking-wide">Fair Value Gaps</h3>
          <div className="flex gap-4 text-xs mb-2">
            <span className="text-green-400">Bullish: {fvg.bullish_gaps}</span>
            <span className="text-red-400">Bearish: {fvg.bearish_gaps}</span>
          </div>
          {fvg.nearest?.map((f, i) => (
              <div key={`fvg-${i}`} className="flex justify-between text-xs mt-1">
                <span className={f.type === "bullish" ? "text-green-400" : "text-red-400"}>
                  {f.type.toUpperCase()}
                </span>
                <span className="text-gray-400 font-mono">{f.range}</span>
              </div>
            ))}
        </div>
      )}
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  Main Page Component                                               */
/* ------------------------------------------------------------------ */

export function ProAnalysisPage() {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [asset, setAsset] = useState<string>("BTC/USDT");
  const [timeframe, setTimeframe] = useState("4h");
  const [imageBase64, setImageBase64] = useState<string | null>(null);
  const [imagePreview, setImagePreview] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const chatEndRef = useRef<HTMLDivElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  // Latest response data for sidebar
  const latestResponse = messages
    .filter((m) => m.role === "assistant" && m.marketData)
    .at(-1)?.marketData ?? null;

  // Auto-scroll
  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading]);

  // Auto-resize textarea
  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = "auto";
      textareaRef.current.style.height = `${Math.min(textareaRef.current.scrollHeight, 200)}px`;
    }
  }, [input]);

  const handleImageUpload = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    if (file.size > MAX_IMAGE_SIZE) {
      setError("Image exceeds 5MB limit. Please use a smaller image.");
      return;
    }

    const reader = new FileReader();
    reader.onload = () => {
      const result = reader.result as string;
      const base64Data = result.split(",")[1] ?? null;
      setImageBase64(base64Data);
      setImagePreview(result);
      setError(null);
    };
    reader.readAsDataURL(file);
  }, []);

  const removeImage = useCallback(() => {
    setImageBase64(null);
    setImagePreview(null);
    if (fileInputRef.current) fileInputRef.current.value = "";
  }, []);

  const sendMessage = useCallback(
    async (text?: string) => {
      const msg = text ?? input.trim();
      if (!msg && !imageBase64) return;

      const userMessage: ChatMessage = {
        role: "user",
        content: msg || "(image uploaded)",
        imagePreview: imagePreview ?? undefined,
      };

      setMessages((prev) => [...prev, userMessage]);
      setInput("");
      setError(null);
      setLoading(true);

      // Build history for API
      const history = messages.map((m) => ({
        role: m.role,
        content: m.content,
      }));

      try {
        const data = await sendProAnalysis(msg, asset, timeframe, imageBase64, history);
        const assistantMessage: ChatMessage = {
          role: "assistant",
          content: data.analysis,
          marketData: data,
        };
        setMessages((prev) => [...prev, assistantMessage]);
      } catch (err: unknown) {
        const errorMsg =
          err instanceof Error ? err.message : "Failed to get analysis. Please try again.";
        setError(errorMsg);
      } finally {
        setLoading(false);
        removeImage();
      }
    },
    [input, imageBase64, imagePreview, messages, asset, timeframe, removeImage],
  );

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        sendMessage();
      }
    },
    [sendMessage],
  );

  const handleQuickPrompt = useCallback(
    (prompt: string) => {
      sendMessage(prompt);
    },
    [sendMessage],
  );

  return (
    <div className="flex h-[calc(100vh-64px)] gap-4" role="main" aria-label="Pro Analysis page">
      {/* ---- LEFT: Chat Panel ---- */}
      <div className="flex w-[60%] flex-col rounded-lg border border-gray-700 bg-gray-900" role="region" aria-label="Analysis chat">
        {/* Chat header */}
        <div className="flex items-center gap-3 border-b border-gray-700 px-4 py-3">
          <h2 className="text-lg font-bold text-white">Pro Analysis</h2>
          <select
            value={asset}
            onChange={(e) => { setAsset(e.target.value); }}
            className="rounded bg-gray-800 border border-gray-600 px-3 py-1.5 text-sm text-white focus:border-blue-500 focus:outline-none"
            aria-label="Select trading pair"
          >
            {ASSETS.map((a) => (
              <option key={a} value={a}>
                {a}
              </option>
            ))}
          </select>
          <select
            value={timeframe}
            onChange={(e) => { setTimeframe(e.target.value); }}
            className="rounded bg-gray-800 border border-gray-600 px-3 py-1.5 text-sm text-white focus:border-blue-500 focus:outline-none"
            aria-label="Select timeframe"
          >
            {TIMEFRAMES.map((tf) => (
              <option key={tf.value} value={tf.value}>
                {tf.label}
              </option>
            ))}
          </select>
        </div>

        {/* Quick prompts */}
        <div className="flex flex-wrap gap-2 border-b border-gray-700 px-4 py-2">
          {QUICK_PROMPTS.map((prompt) => (
            <button
              key={prompt}
              onClick={() => { handleQuickPrompt(prompt); }}
              disabled={loading}
              className="rounded-full bg-gray-800 px-3 py-1 text-xs text-gray-300 transition-colors hover:bg-gray-700 hover:text-white disabled:opacity-50"
              aria-label={`Quick prompt: ${prompt}`}
            >
              {prompt}
            </button>
          ))}
        </div>

        {/* Messages */}
        <div className="flex-1 overflow-y-auto px-4 py-4 space-y-4" role="log" aria-label="Chat messages" aria-live="polite">
          {messages.length === 0 && (
            <div className="flex h-full items-center justify-center">
              <div className="text-center">
                <p className="text-2xl font-bold text-gray-500 mb-2">Pro Analysis Chat</p>
                <p className="text-sm text-gray-600">
                  Select a pair and timeframe, then ask for professional technical analysis.
                </p>
                <p className="text-xs text-gray-700 mt-1">
                  You can also upload chart screenshots for visual analysis.
                </p>
              </div>
            </div>
          )}

          {messages.map((msg, idx) => (
            <div
              key={idx}
              className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"}`}
            >
              <div
                className={`max-w-[85%] rounded-lg px-4 py-3 ${
                  msg.role === "user"
                    ? "bg-blue-900/60 text-white"
                    : "bg-gray-800 text-gray-200"
                }`}
                role="article"
                aria-label={`${msg.role === "user" ? "Your" : "AI"} message`}
              >
                {msg.imagePreview && (
                  <img
                    src={msg.imagePreview}
                    alt="Uploaded chart"
                    className="mb-2 max-h-48 rounded border border-gray-600"
                  />
                )}
                {msg.role === "assistant" ? (
                  <div
                    className="prose prose-invert max-w-none text-sm leading-relaxed"
                    dangerouslySetInnerHTML={{ __html: renderMarkdown(msg.content) }}
                  />
                ) : (
                  <p className="text-sm whitespace-pre-wrap">{msg.content}</p>
                )}
              </div>
            </div>
          ))}

          {loading && (
            <div className="flex justify-start">
              <div className="rounded-lg bg-gray-800 px-4 py-3" role="status" aria-label="Loading analysis">
                <div className="flex items-center gap-2">
                  <div className="flex gap-1">
                    <div className="h-2 w-2 rounded-full bg-blue-400 animate-bounce" style={{ animationDelay: "0ms" }} />
                    <div className="h-2 w-2 rounded-full bg-blue-400 animate-bounce" style={{ animationDelay: "150ms" }} />
                    <div className="h-2 w-2 rounded-full bg-blue-400 animate-bounce" style={{ animationDelay: "300ms" }} />
                  </div>
                  <span className="text-sm text-gray-400">Analyzing {asset} on {timeframe}...</span>
                </div>
              </div>
            </div>
          )}

          {error && (
            <div className="rounded-lg border border-red-700 bg-red-950/40 px-4 py-3" role="alert">
              <p className="text-sm text-red-400">{error}</p>
            </div>
          )}

          <div ref={chatEndRef} />
        </div>

        {/* Image preview */}
        {imagePreview && (
          <div className="flex items-center gap-2 border-t border-gray-700 px-4 py-2">
            <img src={imagePreview} alt="Preview of uploaded chart" className="h-12 rounded border border-gray-600" />
            <span className="text-xs text-gray-400">Chart attached</span>
            <button
              onClick={removeImage}
              className="ml-auto rounded bg-gray-700 px-2 py-0.5 text-xs text-gray-300 hover:bg-gray-600"
              aria-label="Remove attached image"
            >
              Remove
            </button>
          </div>
        )}

        {/* Input area */}
        <div className="border-t border-gray-700 px-4 py-3">
          <div className="flex items-end gap-2">
            <input
              ref={fileInputRef}
              type="file"
              accept="image/*"
              onChange={handleImageUpload}
              className="hidden"
              aria-label="Upload chart screenshot"
            />
            <button
              onClick={() => fileInputRef.current?.click()}
              disabled={loading}
              className="flex-shrink-0 rounded bg-gray-700 p-2 text-gray-300 transition-colors hover:bg-gray-600 hover:text-white disabled:opacity-50"
              aria-label="Attach chart image"
              title="Upload chart screenshot (max 5MB)"
            >
              <svg xmlns="http://www.w3.org/2000/svg" className="h-5 w-5" viewBox="0 0 20 20" fill="currentColor">
                <path
                  fillRule="evenodd"
                  d="M4 3a2 2 0 00-2 2v10a2 2 0 002 2h12a2 2 0 002-2V5a2 2 0 00-2-2H4zm12 12H4l4-8 3 6 2-4 3 6z"
                  clipRule="evenodd"
                />
              </svg>
            </button>
            <textarea
              ref={textareaRef}
              value={input}
              onChange={(e) => { setInput(e.target.value); }}
              onKeyDown={handleKeyDown}
              placeholder={`Ask about ${asset}... (Shift+Enter for new line)`}
              disabled={loading}
              rows={1}
              className="flex-1 resize-none rounded bg-gray-800 border border-gray-600 px-3 py-2 text-sm text-white placeholder-gray-500 focus:border-blue-500 focus:outline-none disabled:opacity-50"
              aria-label="Type your analysis question"
            />
            <button
              onClick={() => sendMessage()}
              disabled={loading || (!input.trim() && !imageBase64)}
              className="flex-shrink-0 rounded bg-blue-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-blue-500 disabled:bg-gray-700 disabled:text-gray-500"
              aria-label="Send message"
            >
              {loading ? "Analyzing..." : "Send"}
            </button>
          </div>
        </div>
      </div>

      {/* ---- RIGHT: Data Sidebar ---- */}
      <div
        className="w-[40%] overflow-y-auto rounded-lg border border-gray-700 bg-gray-900 p-4 space-y-4"
        role="complementary"
        aria-label="Market data sidebar"
      >
        {latestResponse ? (
          <>
            {/* Probability Gauge */}
            <ProbabilityGauge
              long={latestResponse.probability.long}
              short={latestResponse.probability.short}
            />

            {/* Probability Components */}
            {latestResponse.probability.components && (
              <div className="rounded-lg border border-gray-700 bg-gray-800 p-4" role="region" aria-label="Probability components">
                <h3 className="mb-2 text-sm font-semibold text-gray-400 uppercase tracking-wide">Score Components</h3>
                <div className="space-y-1 text-xs">
                  {Object.entries(latestResponse.probability.components).map(([key, val]) => (
                    <div key={key} className="flex justify-between">
                      <span className="text-gray-500">{key.replace(/_/g, " ")}</span>
                      <span
                        className={`font-mono ${
                          typeof val === "number" && val > 0
                            ? "text-green-400"
                            : typeof val === "number" && val < 0
                              ? "text-red-400"
                              : "text-gray-300"
                        }`}
                      >
                        {typeof val === "number" ? val.toFixed(3) : String(val)}
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Recommendation */}
            {latestResponse.recommendation && (
              <RecommendationCard rec={latestResponse.recommendation} />
            )}

            {/* Market Data */}
            <MarketDataPanel data={latestResponse.market_data} />
          </>
        ) : (
          <div className="flex h-full items-center justify-center">
            <div className="text-center">
              <div className="mx-auto mb-3 h-16 w-16 rounded-full bg-gray-800 flex items-center justify-center">
                <svg xmlns="http://www.w3.org/2000/svg" className="h-8 w-8 text-gray-600" viewBox="0 0 20 20" fill="currentColor">
                  <path d="M2 11a1 1 0 011-1h2a1 1 0 011 1v5a1 1 0 01-1 1H3a1 1 0 01-1-1v-5zm6-4a1 1 0 011-1h2a1 1 0 011 1v9a1 1 0 01-1 1H9a1 1 0 01-1-1V7zm6-3a1 1 0 011-1h2a1 1 0 011 1v12a1 1 0 01-1 1h-2a1 1 0 01-1-1V4z" />
                </svg>
              </div>
              <p className="text-sm text-gray-500">Market data will appear here</p>
              <p className="text-xs text-gray-600 mt-1">after your first analysis request</p>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
