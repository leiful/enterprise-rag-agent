export const API_BASE = import.meta.env.VITE_API_BASE || "http://localhost:8000";

export const DEFAULT_RAG_EVAL_SUITES = [
  { id: "core", name: "Core Regression", question_count: 20 },
  { id: "acceptance", name: "Acceptance", question_count: 12 },
  { id: "ragbench", name: "RAGBench Sample", question_count: 5 },
  { id: "uploaded_pdfs", name: "Uploaded PDF Baseline", question_count: 37 },
];

export const EMPTY_MESSAGE = {
  role: "assistant",
  content: "Ready. Ask me to inspect project files, explain code, or run safe checks.",
};

export const PAGE_SIZE = 8;
export const DAILY_TOKEN_WARNING_THRESHOLD = 1000000;
