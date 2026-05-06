import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Activity,
  Bot,
  CheckCircle2,
  Clipboard,
  Database,
  FileUp,
  Loader2,
  PanelRight,
  Search,
  Send,
  Sparkles,
  User,
} from "lucide-react";
import { FormEvent, useMemo, useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { MarkdownMessage } from "@/components/markdown-message";
import {
  API_BASE_URL,
  getReadiness,
  ingestFile,
  ingestText,
  searchRag,
  streamAgent,
  type RagSource,
} from "@/lib/api";
import { cn } from "@/lib/utils";

type Message = {
  id: string;
  role: "user" | "agent";
  content: string;
  sources?: RagSource[];
};

const examples = [
  "Create a production launch checklist for this agent.",
  "What observability should I add before going live?",
  "Design a tool-calling roadmap for a SaaS support agent.",
  "Humanize this draft in my voice: Dear customer, your request has been processed successfully.",
];

function createId() {
  return crypto.randomUUID();
}

export default function App() {
  const queryClient = useQueryClient();
  const [threadId, setThreadId] = useState("demo-thread");
  const [streaming, setStreaming] = useState(false);
  const [draft, setDraft] = useState(examples[0]);
  const [knowledgeSource, setKnowledgeSource] = useState("manual-note");
  const [knowledgeText, setKnowledgeText] = useState("");
  const [documentType, setDocumentType] = useState<"knowledge" | "voice_sample">("knowledge");
  const [searchQuery, setSearchQuery] = useState("");
  const [searchResults, setSearchResults] = useState<RagSource[]>([]);
  const [messages, setMessages] = useState<Message[]>([
    {
      id: createId(),
      role: "agent",
      content: "Ready. Point me at the thing you want this agent to reason through.",
    },
  ]);

  const readiness = useQuery({
    queryKey: ["readiness"],
    queryFn: getReadiness,
    refetchInterval: 10_000,
    retry: false,
  });

  const runStream = async (input: { message: string; thread_id?: string }) => {
    const responseId = createId();
    setStreaming(true);
    setMessages((current) => [...current, { id: responseId, role: "agent", content: "" }]);
    try {
      for await (const event of streamAgent(input)) {
        if (event.type === "delta") {
          setMessages((current) =>
            current.map((message) =>
              message.id === responseId
                ? { ...message, content: message.content + event.text }
                : message,
            ),
          );
        } else if (event.type === "sources") {
          setMessages((current) =>
            current.map((message) =>
              message.id === responseId ? { ...message, sources: event.sources } : message,
            ),
          );
        }
      }
    } catch (error) {
      toast.error("Agent request failed", {
        description: error instanceof Error ? error.message : "Unknown error",
      });
      setMessages((current) => current.filter((message) => message.id !== responseId));
    } finally {
      setStreaming(false);
    }
  };

  const textIngestion = useMutation({
    mutationFn: ingestText,
    onSuccess: (response) => {
      setKnowledgeText("");
      toast.success(
        documentType === "voice_sample" ? "Voice sample ingested" : "Knowledge ingested",
        {
          description: `${response.source}: ${response.chunks} chunks`,
        },
      );
      void queryClient.invalidateQueries({ queryKey: ["rag-search"] });
    },
    onError: (error) => {
      toast.error("RAG ingestion failed", {
        description: error instanceof Error ? error.message : "Unknown error",
      });
    },
  });

  const fileIngestion = useMutation({
    mutationFn: ({ file, type }: { file: File; type: "knowledge" | "voice_sample" }) =>
      ingestFile(file, type),
    onSuccess: (response) => {
      toast.success("File ingested", {
        description: `${response.source}: ${response.chunks} chunks`,
      });
      void queryClient.invalidateQueries({ queryKey: ["rag-search"] });
    },
    onError: (error) => {
      toast.error("File ingestion failed", {
        description: error instanceof Error ? error.message : "Unknown error",
      });
    },
  });

  const ragSearch = useMutation({
    mutationKey: ["rag-search"],
    mutationFn: searchRag,
    onSuccess: (response) => {
      setSearchResults(response.sources);
    },
    onError: (error) => {
      toast.error("RAG search failed", {
        description: error instanceof Error ? error.message : "Unknown error",
      });
    },
  });

  const status = useMemo(() => {
    if (readiness.isLoading) return "Checking";
    if (readiness.data) return "Ready";
    return "Offline";
  }, [readiness.data, readiness.isLoading]);

  function submitMessage(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const message = draft.trim();
    if (!message || streaming) return;

    setMessages((current) => [...current, { id: createId(), role: "user", content: message }]);
    setDraft("");
    void runStream({ message, thread_id: threadId || undefined });
  }

  async function copyTranscript() {
    const transcript = messages
      .map((message) => `${message.role === "user" ? "User" : "Agent"}: ${message.content}`)
      .join("\n\n");
    await navigator.clipboard.writeText(transcript);
    toast.success("Transcript copied");
  }

  return (
    <main className="h-dvh bg-stone-50 text-zinc-950">
      <div className="grid h-full lg:grid-cols-[1fr_360px]">
        <section className="flex h-full min-h-0 flex-col">
          <header className="shrink-0 border-b border-zinc-200 bg-white">
            <div className="flex min-h-16 flex-wrap items-center justify-between gap-3 px-4 py-3 sm:px-6">
              <div className="flex items-center gap-3">
                <div className="flex size-10 items-center justify-center rounded-md bg-zinc-950 text-white">
                  <Bot className="size-5" aria-hidden="true" />
                </div>
                <div>
                  <h1 className="text-base font-semibold tracking-normal">AI Agent Console</h1>
                  <p className="text-sm text-zinc-500">FastAPI + LangChain + LangGraph</p>
                </div>
              </div>
              <div className="flex items-center gap-2">
                <span
                  className={cn(
                    "inline-flex h-8 items-center gap-2 rounded-md border px-3 text-xs font-medium",
                    readiness.data
                      ? "border-emerald-200 bg-emerald-50 text-emerald-700"
                      : "border-zinc-200 bg-zinc-100 text-zinc-600",
                  )}
                >
                  <Activity className="size-3.5" aria-hidden="true" />
                  {status}
                </span>
                <Button type="button" variant="secondary" size="sm" onClick={copyTranscript}>
                  <Clipboard className="size-4" aria-hidden="true" />
                  Copy
                </Button>
              </div>
            </div>
          </header>

          <div className="min-h-0 flex-1 scroll-pb-48 overflow-y-auto px-4 py-6 sm:px-6">
            <div className="mx-auto flex max-w-4xl flex-col gap-4">
              {messages.map((message) => (
                <article
                  key={message.id}
                  className={cn(
                    "flex gap-3",
                    message.role === "user" ? "justify-end" : "justify-start",
                  )}
                >
                  {message.role === "agent" ? (
                    <div className="mt-1 flex size-8 shrink-0 items-center justify-center rounded-md bg-zinc-950 text-white">
                      <Sparkles className="size-4" aria-hidden="true" />
                    </div>
                  ) : null}
                  <div
                    className={cn(
                      "max-w-[min(760px,calc(100vw-2rem))] rounded-md px-4 py-3 text-sm leading-6 shadow-sm",
                      message.role === "user"
                        ? "bg-blue-600 text-white"
                        : "border border-zinc-200 bg-white text-zinc-800",
                    )}
                  >
                    {message.role === "agent" ? (
                      <div className="markdown-message">
                        <MarkdownMessage content={message.content} />
                      </div>
                    ) : (
                      <p className="whitespace-pre-wrap break-words">{message.content}</p>
                    )}
                    {message.sources?.length ? (
                      <div className="mt-3 border-t border-zinc-200 pt-3">
                        <p className="text-xs font-semibold uppercase text-zinc-500">Sources</p>
                        <div className="mt-2 space-y-2">
                          {message.sources.map((source, index) => (
                            <div key={`${source.source}-${index}`} className="text-xs text-zinc-600">
                              <span className="font-medium text-zinc-800">{source.source}</span>
                              {typeof source.score === "number" ? (
                                <span> · {source.score.toFixed(3)}</span>
                              ) : null}
                            </div>
                          ))}
                        </div>
                      </div>
                    ) : null}
                  </div>
                  {message.role === "user" ? (
                    <div className="mt-1 flex size-8 shrink-0 items-center justify-center rounded-md bg-blue-600 text-white">
                      <User className="size-4" aria-hidden="true" />
                    </div>
                  ) : null}
                </article>
              ))}
              {streaming ? (
                <div className="flex items-center gap-3 text-sm text-zinc-500">
                  <Loader2 className="size-4 animate-spin" aria-hidden="true" />
                  Thinking
                </div>
              ) : null}
            </div>
          </div>

          <form
            onSubmit={submitMessage}
            className="sticky bottom-0 z-20 shrink-0 border-t border-zinc-200 bg-white p-4 shadow-[0_-12px_30px_rgba(24,24,27,0.06)] sm:p-6"
          >
            <div className="mx-auto flex max-w-4xl flex-col gap-3">
              <textarea
                value={draft}
                onChange={(event) => setDraft(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === "Enter" && !event.shiftKey) {
                    event.preventDefault();
                    event.currentTarget.form?.requestSubmit();
                  }
                }}
                rows={2}
                maxLength={16_000}
                className="max-h-40 min-h-16 resize-none rounded-md border border-zinc-200 bg-white p-3 text-sm leading-6 outline-none transition focus:border-zinc-400 focus:ring-2 focus:ring-zinc-950/10"
                placeholder="Ask the agent... (Enter to send, Shift+Enter for newline)"
              />
              <div className="flex flex-wrap items-center justify-between gap-3">
                <input
                  value={threadId}
                  onChange={(event) => setThreadId(event.target.value)}
                  className="h-10 w-full rounded-md border border-zinc-200 bg-white px-3 text-sm outline-none transition focus:border-zinc-400 focus:ring-2 focus:ring-zinc-950/10 sm:w-64"
                  placeholder="thread id"
                />
                <Button type="submit" disabled={streaming || !draft.trim()}>
                  {streaming ? (
                    <Loader2 className="size-4 animate-spin" aria-hidden="true" />
                  ) : (
                    <Send className="size-4" aria-hidden="true" />
                  )}
                  Send
                </Button>
              </div>
            </div>
          </form>
        </section>

        <aside className="min-h-0 overflow-y-auto border-t border-zinc-200 bg-white p-5 lg:border-l lg:border-t-0">
          <div className="flex items-center gap-2 text-sm font-semibold">
            <PanelRight className="size-4" aria-hidden="true" />
            Test Bench
          </div>

          <div className="mt-5 space-y-3">
            {examples.map((example) => (
              <button
                key={example}
                type="button"
                onClick={() => setDraft(example)}
                className="w-full rounded-md border border-zinc-200 bg-white p-3 text-left text-sm leading-5 text-zinc-700 transition hover:border-zinc-300 hover:bg-zinc-50"
              >
                {example}
              </button>
            ))}
          </div>

          <div className="mt-6 rounded-md border border-zinc-200 bg-zinc-50 p-4">
            <div className="flex items-center gap-2 text-sm font-medium text-zinc-800">
              <Database className="size-4 text-blue-600" aria-hidden="true" />
              Knowledge
            </div>
            <div className="mt-4 space-y-3">
              <input
                value={knowledgeSource}
                onChange={(event) => setKnowledgeSource(event.target.value)}
                className="h-10 w-full rounded-md border border-zinc-200 bg-white px-3 text-sm outline-none transition focus:border-zinc-400 focus:ring-2 focus:ring-zinc-950/10"
                placeholder="source name"
              />
              <div className="grid grid-cols-2 rounded-md border border-zinc-200 bg-white p-1">
                <button
                  type="button"
                  onClick={() => setDocumentType("knowledge")}
                  className={cn(
                    "h-8 rounded px-3 text-xs font-medium transition",
                    documentType === "knowledge"
                      ? "bg-zinc-950 text-white"
                      : "text-zinc-600 hover:bg-zinc-100",
                  )}
                >
                  Knowledge
                </button>
                <button
                  type="button"
                  onClick={() => setDocumentType("voice_sample")}
                  className={cn(
                    "h-8 rounded px-3 text-xs font-medium transition",
                    documentType === "voice_sample"
                      ? "bg-zinc-950 text-white"
                      : "text-zinc-600 hover:bg-zinc-100",
                  )}
                >
                  Voice
                </button>
              </div>
              <textarea
                value={knowledgeText}
                onChange={(event) => setKnowledgeText(event.target.value)}
                rows={5}
                className="min-h-28 w-full resize-none rounded-md border border-zinc-200 bg-white p-3 text-sm leading-5 outline-none transition focus:border-zinc-400 focus:ring-2 focus:ring-zinc-950/10"
                placeholder={
                  documentType === "voice_sample"
                    ? "Paste something you wrote..."
                    : "Paste text to add to RAG..."
                }
              />
              <div className="grid grid-cols-2 gap-2">
                <Button
                  type="button"
                  variant="secondary"
                  disabled={!knowledgeText.trim() || !knowledgeSource.trim() || textIngestion.isPending}
                  onClick={() =>
                    textIngestion.mutate({
                      source: knowledgeSource,
                      text: knowledgeText,
                      documentType,
                    })
                  }
                >
                  {textIngestion.isPending ? (
                    <Loader2 className="size-4 animate-spin" aria-hidden="true" />
                  ) : (
                    <Database className="size-4" aria-hidden="true" />
                  )}
                  Add
                </Button>
                <label className="inline-flex h-10 cursor-pointer items-center justify-center gap-2 rounded-md border border-zinc-200 bg-white px-4 text-sm font-medium text-zinc-900 transition hover:bg-zinc-100">
                  <FileUp className="size-4" aria-hidden="true" />
                  File
                  <input
                    type="file"
                    className="sr-only"
                    accept=".txt,.md,.markdown,.json,.pdf"
                    onChange={(event) => {
                      const file = event.target.files?.[0];
                      if (file) fileIngestion.mutate({ file, type: documentType });
                      event.currentTarget.value = "";
                    }}
                  />
                </label>
              </div>
              <div className="flex gap-2">
                <input
                  value={searchQuery}
                  onChange={(event) => setSearchQuery(event.target.value)}
                  className="h-10 min-w-0 flex-1 rounded-md border border-zinc-200 bg-white px-3 text-sm outline-none transition focus:border-zinc-400 focus:ring-2 focus:ring-zinc-950/10"
                  placeholder="test retrieval"
                />
                <Button
                  type="button"
                  size="icon"
                  variant="secondary"
                  disabled={!searchQuery.trim() || ragSearch.isPending}
                  onClick={() => ragSearch.mutate(searchQuery)}
                  aria-label="Search knowledge"
                >
                  {ragSearch.isPending ? (
                    <Loader2 className="size-4 animate-spin" aria-hidden="true" />
                  ) : (
                    <Search className="size-4" aria-hidden="true" />
                  )}
                </Button>
              </div>
              {searchResults.length ? (
                <div className="space-y-2">
                  {searchResults.map((source, index) => (
                    <div
                      key={`${source.source}-${index}`}
                      className="rounded-md border border-zinc-200 bg-white p-3 text-xs leading-5 text-zinc-600"
                    >
                      <div className="font-medium text-zinc-800">
                        {source.source}
                        {typeof source.score === "number" ? ` · ${source.score.toFixed(3)}` : ""}
                      </div>
                      <p className="mt-1 line-clamp-4">{source.content}</p>
                    </div>
                  ))}
                </div>
              ) : null}
            </div>
          </div>

          <div className="mt-6 rounded-md border border-zinc-200 bg-zinc-50 p-4">
            <div className="flex items-center gap-2 text-sm font-medium text-zinc-800">
              <CheckCircle2 className="size-4 text-emerald-600" aria-hidden="true" />
              Runtime
            </div>
            <dl className="mt-4 space-y-3 text-sm">
              <div className="flex items-center justify-between gap-4">
                <dt className="text-zinc-500">API</dt>
                <dd className="truncate font-medium text-zinc-800">{API_BASE_URL}</dd>
              </div>
              <div className="flex items-center justify-between gap-4">
                <dt className="text-zinc-500">UI</dt>
                <dd className="font-medium text-zinc-800">5173</dd>
              </div>
              <div className="flex items-center justify-between gap-4">
                <dt className="text-zinc-500">Thread</dt>
                <dd className="max-w-36 truncate font-medium text-zinc-800">{threadId || "none"}</dd>
              </div>
            </dl>
          </div>
        </aside>
      </div>
    </main>
  );
}
