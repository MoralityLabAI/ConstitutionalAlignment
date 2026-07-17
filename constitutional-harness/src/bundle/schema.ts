import { createHash } from 'crypto';
import * as fs from 'fs';
import * as path from 'path';

export const BUNDLE_SUITES = [
  'storyworld',
  'identity_behavior',
  'pressure',
  'helpfulness',
  'theology_guardrail'
] as const;

export type BundleSuite = typeof BUNDLE_SUITES[number];
export type BlindedCondition = 'C1' | 'C2' | 'C3' | 'C4' | 'C5';
export type JsonValue = null | boolean | number | string | JsonValue[] | {
  [key: string]: JsonValue;
};

export interface BundleMessage {
  role: 'system' | 'developer' | 'user' | 'assistant' | 'tool';
  content: string;
}

export interface BundleRowPayload {
  example_id: string;
  blinded_condition: BlindedCondition;
  suite: BundleSuite;
  world_id?: string;
  messages: BundleMessage[];
  response: string;
  sampling_meta: Record<string, JsonValue>;
}

export interface BundleResponseRow extends BundleRowPayload {
  sha256: string;
}

export interface LoadedBundle {
  bundleDir: string;
  responsesPath: string;
  rows: BundleResponseRow[];
}

const ALLOWED_ROW_KEYS = new Set([
  'example_id',
  'blinded_condition',
  'suite',
  'world_id',
  'messages',
  'response',
  'sampling_meta',
  'sha256'
]);
const ALLOWED_MESSAGE_KEYS = new Set(['role', 'content']);
const MESSAGE_ROLES = new Set(['system', 'developer', 'user', 'assistant', 'tool']);
const SHA256_PATTERN = /^[a-f0-9]{64}$/;
const CONDITION_PATTERN = /^C[1-5]$/;

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function validateJsonValue(value: unknown, location: string): asserts value is JsonValue {
  if (value === null || typeof value === 'string' || typeof value === 'boolean') {
    return;
  }
  if (typeof value === 'number') {
    if (!Number.isFinite(value)) {
      throw new Error(`${location} must contain only finite JSON numbers`);
    }
    return;
  }
  if (Array.isArray(value)) {
    value.forEach((item, index) => validateJsonValue(item, `${location}[${index}]`));
    return;
  }
  if (isRecord(value)) {
    for (const [key, item] of Object.entries(value)) {
      validateJsonValue(item, `${location}.${key}`);
    }
    return;
  }
  throw new Error(`${location} must be valid JSON`);
}

function rejectUnblindedMetadata(value: JsonValue, location: string): void {
  if (Array.isArray(value)) {
    value.forEach((item, index) => rejectUnblindedMetadata(item, `${location}[${index}]`));
    return;
  }
  if (typeof value !== 'object' || value === null) {
    return;
  }
  const forbiddenKey = /^(?:condition(?:_label|_name)?|unblinded_condition|arm(?:_label|_name)?|treatment(?:_label|_name)?|blinding_map)$/i;
  for (const [key, item] of Object.entries(value)) {
    if (forbiddenKey.test(key)) {
      throw new Error(`${location}.${key} is forbidden unblinded condition metadata`);
    }
    rejectUnblindedMetadata(item, `${location}.${key}`);
  }
}

function canonicalize(value: JsonValue): string {
  if (value === null || typeof value === 'boolean' || typeof value === 'number' ||
      typeof value === 'string') {
    return JSON.stringify(value);
  }
  if (Array.isArray(value)) {
    return `[${value.map(item => canonicalize(item)).join(',')}]`;
  }
  const entries = Object.keys(value).sort().map(key =>
    `${JSON.stringify(key)}:${canonicalize(value[key])}`
  );
  return `{${entries.join(',')}}`;
}

export function canonicalJson(value: JsonValue): string {
  validateJsonValue(value, 'canonical JSON input');
  return canonicalize(value);
}

export function bundleRowPayload(row: BundleResponseRow): BundleRowPayload {
  const payload: BundleRowPayload = {
    example_id: row.example_id,
    blinded_condition: row.blinded_condition,
    suite: row.suite,
    messages: row.messages,
    response: row.response,
    sampling_meta: row.sampling_meta
  };
  if (row.world_id !== undefined) {
    payload.world_id = row.world_id;
  }
  return payload;
}

export function computeBundleRowSha256(payload: BundleRowPayload): string {
  return createHash('sha256')
    .update(canonicalJson(payload as unknown as JsonValue), 'utf8')
    .digest('hex');
}

function requireNonEmptyString(value: unknown, location: string): string {
  if (typeof value !== 'string' || value.trim().length === 0) {
    throw new Error(`${location} must be a non-empty string`);
  }
  return value;
}

function validateMessage(value: unknown, location: string): BundleMessage {
  if (!isRecord(value)) {
    throw new Error(`${location} must be an object`);
  }
  const unexpected = Object.keys(value).filter(key => !ALLOWED_MESSAGE_KEYS.has(key));
  if (unexpected.length > 0) {
    throw new Error(`${location} contains unexpected field(s): ${unexpected.join(', ')}`);
  }
  if (typeof value.role !== 'string' || !MESSAGE_ROLES.has(value.role)) {
    throw new Error(`${location}.role must be system, developer, user, assistant, or tool`);
  }
  return {
    role: value.role as BundleMessage['role'],
    content: requireNonEmptyString(value.content, `${location}.content`)
  };
}

export function validateBundleRow(value: unknown, lineNumber: number): BundleResponseRow {
  const location = `responses.jsonl line ${lineNumber}`;
  if (!isRecord(value)) {
    throw new Error(`${location} must be a JSON object`);
  }
  const unexpected = Object.keys(value).filter(key => !ALLOWED_ROW_KEYS.has(key));
  if (unexpected.length > 0) {
    throw new Error(
      `${location} contains unexpected field(s): ${unexpected.join(', ')}; ` +
      'unblinded condition metadata is forbidden'
    );
  }

  const exampleId = requireNonEmptyString(value.example_id, `${location}.example_id`);
  if (typeof value.blinded_condition !== 'string' ||
      !CONDITION_PATTERN.test(value.blinded_condition)) {
    throw new Error(`${location}.blinded_condition must be one of C1, C2, C3, C4, C5`);
  }
  if (typeof value.suite !== 'string' ||
      !BUNDLE_SUITES.some(suite => suite === value.suite)) {
    throw new Error(`${location}.suite must be one of ${BUNDLE_SUITES.join(', ')}`);
  }
  if (value.world_id !== undefined &&
      (typeof value.world_id !== 'string' || value.world_id.trim().length === 0)) {
    throw new Error(`${location}.world_id must be a non-empty string when present`);
  }
  if (!Array.isArray(value.messages) || value.messages.length === 0) {
    throw new Error(`${location}.messages must be a non-empty array`);
  }
  const messages = value.messages.map((message, index) =>
    validateMessage(message, `${location}.messages[${index}]`)
  );
  const response = requireNonEmptyString(value.response, `${location}.response`);
  if (!isRecord(value.sampling_meta)) {
    throw new Error(`${location}.sampling_meta must be a JSON object`);
  }
  validateJsonValue(value.sampling_meta, `${location}.sampling_meta`);
  rejectUnblindedMetadata(value.sampling_meta as JsonValue, `${location}.sampling_meta`);
  if (typeof value.sha256 !== 'string' || !SHA256_PATTERN.test(value.sha256)) {
    throw new Error(`${location}.sha256 must be a lowercase 64-character SHA-256 digest`);
  }

  const row: BundleResponseRow = {
    example_id: exampleId,
    blinded_condition: value.blinded_condition as BlindedCondition,
    suite: value.suite as BundleSuite,
    messages,
    response,
    sampling_meta: value.sampling_meta as Record<string, JsonValue>,
    sha256: value.sha256
  };
  if (value.world_id !== undefined) {
    row.world_id = value.world_id as string;
  }

  const actualDigest = computeBundleRowSha256(bundleRowPayload(row));
  if (actualDigest !== row.sha256) {
    throw new Error(
      `${location}.sha256 mismatch for example_id ${row.example_id}: ` +
      `expected ${row.sha256}, computed ${actualDigest}`
    );
  }
  return row;
}

function inspectBundleTree(directory: string): void {
  for (const entry of fs.readdirSync(directory, { withFileTypes: true })) {
    if (entry.name.toLowerCase() === 'blinding_map.json') {
      throw new Error(
        `Refusing bundle because prohibited file blinding_map.json is present at ${path.join(directory, entry.name)}`
      );
    }
    const entryPath = path.join(directory, entry.name);
    const stat = fs.lstatSync(entryPath);
    if (stat.isSymbolicLink()) {
      throw new Error(`Refusing bundle containing symbolic link: ${entryPath}`);
    }
    if (stat.isDirectory()) {
      inspectBundleTree(entryPath);
    }
  }
}

export function loadAndValidateBundle(bundleDirectory: string): LoadedBundle {
  const bundleDir = path.resolve(bundleDirectory);
  if (!fs.existsSync(bundleDir) || !fs.statSync(bundleDir).isDirectory()) {
    throw new Error(`Bundle directory does not exist or is not a directory: ${bundleDir}`);
  }

  // Inspect names before opening any bundle file. The blinding map is never loaded.
  inspectBundleTree(bundleDir);

  const responsesPath = path.join(bundleDir, 'responses.jsonl');
  if (!fs.existsSync(responsesPath) || !fs.statSync(responsesPath).isFile()) {
    throw new Error(`Bundle must contain a regular responses.jsonl file: ${responsesPath}`);
  }
  const lines = fs.readFileSync(responsesPath, 'utf8').split(/\r?\n/);
  const rows: BundleResponseRow[] = [];
  const seenIds = new Set<string>();
  for (let index = 0; index < lines.length; index += 1) {
    const line = lines[index];
    if (line.trim().length === 0) {
      continue;
    }
    let parsed: unknown;
    try {
      parsed = JSON.parse(line);
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      throw new Error(`responses.jsonl line ${index + 1} is invalid JSON: ${message}`);
    }
    const row = validateBundleRow(parsed, index + 1);
    if (seenIds.has(row.example_id)) {
      throw new Error(`Duplicate example_id in responses.jsonl: ${row.example_id}`);
    }
    seenIds.add(row.example_id);
    rows.push(row);
  }
  if (rows.length === 0) {
    throw new Error('responses.jsonl must contain at least one response row');
  }
  return { bundleDir, responsesPath, rows };
}
