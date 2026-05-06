export type AgentInvokeRequest = {
  message: string;
  thread_id?: string;
};

export type AgentInvokeResponse = {
  message: string;
  thread_id?: string;
  sources: RagSource[];
};

export type RagSource = {
  source: string;
  content: string;
  score?: number | null;
  metadata: Record<string, unknown>;
};

export type RagIngestResponse = {
  source: string;
  chunks: number;
};

export type RagSearchResponse = {
  query: string;
  sources: RagSource[];
};

export const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://127.0.0.1:8000";
export const API_KEY = import.meta.env.VITE_API_KEY ?? "";

function authHeaders(extra: Record<string, string> = {}): Record<string, string> {
  return API_KEY ? { ...extra, "x-api-key": API_KEY } : extra;
}

export type StreamEvent =
  | { type: "sources"; sources: RagSource[] }
  | { type: "delta"; text: string; node?: string | null }
  | { type: "done"; thread_id?: string };

async function readErrorMessage(response: Response): Promise<string> {
  const body = await response.text();
  if (!body) return `Request failed with ${response.status}`;
  try {
    const parsed = JSON.parse(body) as { detail?: string; title?: string };
    return parsed.detail ?? parsed.title ?? body;
  } catch {
    return body;
  }
}

export async function invokeAgent(request: AgentInvokeRequest): Promise<AgentInvokeResponse> {
  let response: Response;

  try {
    response = await fetch(`${API_BASE_URL}/v1/agent/invoke`, {
      method: "POST",
      headers: authHeaders({ "Content-Type": "application/json" }),
      body: JSON.stringify(request),
    });
  } catch (error) {
    throw new Error(
      `Could not reach the API at ${API_BASE_URL}. Check that FastAPI is running and CORS allows this frontend origin.`,
      { cause: error },
    );
  }

  if (!response.ok) throw new Error(await readErrorMessage(response));

  return response.json() as Promise<AgentInvokeResponse>;
}

export async function* streamAgent(
  request: AgentInvokeRequest,
  options: { signal?: AbortSignal } = {},
): AsyncGenerator<StreamEvent, void, void> {
  const response = await fetch(`${API_BASE_URL}/v1/agent/stream`, {
    method: "POST",
    headers: authHeaders({ "Content-Type": "application/json", Accept: "text/event-stream" }),
    body: JSON.stringify(request),
    signal: options.signal,
  });

  if (!response.ok || !response.body) throw new Error(await readErrorMessage(response));

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    let separator = buffer.indexOf("\n\n");
    while (separator !== -1) {
      const block = buffer.slice(0, separator);
      buffer = buffer.slice(separator + 2);
      const event = parseSseBlock(block);
      if (event) yield event;
      separator = buffer.indexOf("\n\n");
    }
  }
}

function parseSseBlock(block: string): StreamEvent | null {
  let eventName = "message";
  let data = "";
  for (const line of block.split("\n")) {
    if (line.startsWith("event:")) eventName = line.slice(6).trim();
    else if (line.startsWith("data:")) data += line.slice(5).trim();
  }
  if (!data) return null;
  const payload = JSON.parse(data) as Record<string, unknown>;
  return { type: eventName, ...payload } as StreamEvent;
}

export async function getReadiness(): Promise<boolean> {
  const response = await fetch(`${API_BASE_URL}/health/ready`);
  return response.ok;
}

export async function ingestText(input: {
  text: string;
  source: string;
  documentType?: "knowledge" | "voice_sample";
}): Promise<RagIngestResponse> {
  const response = await fetch(`${API_BASE_URL}/v1/rag/documents`, {
    method: "POST",
    headers: authHeaders({ "Content-Type": "application/json" }),
    body: JSON.stringify({
      text: input.text,
      source: input.source,
      document_type: input.documentType ?? "knowledge",
      metadata: { uploaded_from: "frontend" },
    }),
  });

  if (!response.ok) throw new Error(await readErrorMessage(response));

  return response.json() as Promise<RagIngestResponse>;
}

export async function ingestFile(
  file: File,
  documentType: "knowledge" | "voice_sample" = "knowledge",
): Promise<RagIngestResponse> {
  const formData = new FormData();
  formData.append("file", file);
  const path = documentType === "voice_sample" ? "/v1/rag/voice-files" : "/v1/rag/files";

  const response = await fetch(`${API_BASE_URL}${path}`, {
    method: "POST",
    headers: authHeaders(),
    body: formData,
  });

  if (!response.ok) throw new Error(await readErrorMessage(response));

  return response.json() as Promise<RagIngestResponse>;
}

export async function searchRag(query: string): Promise<RagSearchResponse> {
  const params = new URLSearchParams({ q: query });
  const response = await fetch(`${API_BASE_URL}/v1/rag/search?${params.toString()}`, {
    headers: authHeaders(),
  });

  if (!response.ok) throw new Error(await readErrorMessage(response));

  return response.json() as Promise<RagSearchResponse>;
}
