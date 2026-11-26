import type { LogOutputFormat } from "./types";

export type LogLevel = "TRACE" | "DEBUG" | "INFO" | "WARN" | "ERROR" | "FATAL" | "UNKNOWN";
export type LogLevelFilter = "ALL" | LogLevel;

export const LOG_LEVELS: LogLevelFilter[] = ["ALL", "TRACE", "DEBUG", "INFO", "WARN", "ERROR", "FATAL", "UNKNOWN"];

function asObject(value: unknown): Record<string, unknown> | undefined {
  return value !== null && typeof value === "object" && !Array.isArray(value)
    ? value as Record<string, unknown> : undefined;
}

function normalizeLevel(value: unknown): LogLevel | undefined {
  if (typeof value !== "string") return undefined;
  switch (value.trim().toUpperCase()) {
    case "TRACE": return "TRACE";
    case "DEBUG": return "DEBUG";
    case "INFO": case "INFORMATION": case "NOTICE": return "INFO";
    case "WARN": case "WARNING": return "WARN";
    case "ERROR": case "ERR": case "SEVERE": return "ERROR";
    case "FATAL": case "CRITICAL": case "PANIC": return "FATAL";
    default: return undefined;
  }
}

function structuredLevel(value: unknown): LogLevel | undefined {
  const row = asObject(value);
  if (!row) return undefined;
  const log = asObject(row.log);
  return normalizeLevel(row.level) ?? normalizeLevel(row.severity)
    ?? normalizeLevel(row.levelname) ?? normalizeLevel(row.severityText)
    ?? normalizeLevel(row.severity_text) ?? normalizeLevel(row["log.level"])
    ?? normalizeLevel(log?.level);
}

function textLevel(line: string): LogLevel {
  // Standard format wraps each raw Kubernetes line with [current]/[previous].
  // Strip Kubernetes and application timestamps before inspecting the prefix.
  let message = line.trimStart().replace(/^\[(?:current|previous)\]\s*/i, "");
  const timestamp = /^\[?\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(?:[.,]\d+)?(?:Z|[+-]\d{2}:?\d{2})?\]?\s*/;
  message = message.replace(timestamp, "").replace(timestamp, "");
  if (message.startsWith("{")) {
    try {
      const level = structuredLevel(JSON.parse(message));
      if (level) return level;
    } catch { /* Non-JSON messages still use prefix detection. */ }
  }
  const logfmt = message.match(/^(?:\S+\s+){0,5}(?:level|severity)=["']?([a-z]+)\b/i);
  if (logfmt) {
    const level = normalizeLevel(logfmt[1]);
    if (level) return level;
  }
  const prefix = message.match(/^(?:\[[^\]\r\n]+\]\s*)*?\[?(TRACE|DEBUG|INFO(?:RMATION)?|NOTICE|WARN(?:ING)?|ERROR|ERR|SEVERE|FATAL|CRITICAL|PANIC)\b/i);
  return normalizeLevel(prefix?.[1]) ?? "UNKNOWN";
}

export interface FilteredLogs {
  content: string;
  matched: number;
  total: number;
  unit: "lines" | "records";
}

export function filterLogs(content: string, format: LogOutputFormat, query: string, level: LogLevelFilter, matchCase: boolean): FilteredLogs {
  const needle = matchCase ? query.trim() : query.trim().toLowerCase();
  const matchesText = (value: string) => !needle || (matchCase ? value : value.toLowerCase()).includes(needle);
  const matchesLevel = (value: LogLevel) => level === "ALL" || level === value;

  if (format === "json") {
    try {
      const parsed: unknown = JSON.parse(content || "[]");
      if (Array.isArray(parsed)) {
        const records = parsed.filter((record: unknown) => {
          const row = asObject(record);
          const message = typeof row?.message === "string" ? row.message : JSON.stringify(record) ?? "";
          const severity = structuredLevel(row?.payload) ?? structuredLevel(row) ?? textLevel(message);
          return matchesText(message) && matchesLevel(severity);
        });
        return { content: JSON.stringify(records, null, 2), matched: records.length, total: parsed.length, unit: "records" };
      }
    } catch { /* Fall back to line filtering if the response is not valid JSON. */ }
  }

  const lines = content ? content.replace(/\r?\n$/, "").split(/\r?\n/) : [];
  const filtered = lines.filter(line => matchesText(line) && (level === "ALL" || matchesLevel(textLevel(line))));
  return { content: filtered.join("\n"), matched: filtered.length, total: lines.length, unit: "lines" };
}
