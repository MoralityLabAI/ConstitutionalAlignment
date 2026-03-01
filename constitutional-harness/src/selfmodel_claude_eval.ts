/**
 * Evaluate self-model output traces with a Claude-style constitution.
 *
 * This uses the harness verifier path (`verifyText`) against existing outputs
 * rather than generating new model responses.
 */

import * as fs from 'fs';
import * as path from 'path';
import { ConstitutionalHarness } from './harness';
import { ClaudeConstitution } from './constitutions/claude';
import { HarnessConfig, ScenarioContext } from './types';
import { VerificationResult } from './verifiers/base';

interface CliArgs {
  eventsJsonl: string;
  outJson: string;
  outJsonl: string;
}

interface AdapterEventRow {
  encounter_id?: string;
  final_output_preview?: string;
  output_preview?: string;
  normalized_preview?: string;
  label?: string;
  [key: string]: unknown;
}

interface EvalRow {
  ts: string;
  index: number;
  encounter_id: string;
  passed: boolean;
  score_mean: number;
  verifiers: Array<{
    verifier: string;
    passed: boolean;
    score: number;
    violations: number;
  }>;
  violations: Array<{
    type: string;
    severity: string;
    description: string;
    confidence: number;
  }>;
  preview: string;
}

function parseArgs(argv: string[]): CliArgs {
  const args: Record<string, string> = {};
  for (let i = 0; i < argv.length; i += 1) {
    const key = argv[i];
    if (!key.startsWith('--')) {
      continue;
    }
    const value = argv[i + 1];
    if (!value || value.startsWith('--')) {
      throw new Error(`Missing value for argument: ${key}`);
    }
    args[key.slice(2)] = value;
    i += 1;
  }

  const eventsJsonl = args.eventsJsonl;
  const outJson = args.outJson;
  const outJsonl = args.outJsonl;
  if (!eventsJsonl || !outJson || !outJsonl) {
    throw new Error(
      'Usage: tsx src/selfmodel_claude_eval.ts --eventsJsonl <path> --outJson <path> --outJsonl <path>'
    );
  }
  return { eventsJsonl, outJson, outJsonl };
}

function readJsonl(filePath: string): AdapterEventRow[] {
  const lines = fs.readFileSync(filePath, 'utf-8').split(/\r?\n/).filter((line) => line.trim().length > 0);
  const rows: AdapterEventRow[] = [];
  for (const line of lines) {
    try {
      const parsed = JSON.parse(line) as AdapterEventRow;
      rows.push(parsed);
    } catch {
      // Skip malformed rows; caller will surface aggregate counts.
    }
  }
  return rows;
}

function chooseText(row: AdapterEventRow): string {
  const text = row.final_output_preview ?? row.output_preview ?? row.normalized_preview ?? '';
  return String(text || '').trim();
}

function flattenViolations(results: VerificationResult[]): Array<{
  type: string;
  severity: string;
  description: string;
  confidence: number;
}> {
  const out: Array<{ type: string; severity: string; description: string; confidence: number }> = [];
  for (const result of results) {
    for (const v of result.violations) {
      out.push({
        type: v.type,
        severity: v.severity,
        description: v.description,
        confidence: v.confidence
      });
    }
  }
  return out;
}

async function main(): Promise<void> {
  const args = parseArgs(process.argv.slice(2));
  fs.mkdirSync(path.dirname(args.outJson), { recursive: true });
  fs.mkdirSync(path.dirname(args.outJsonl), { recursive: true });

  const config: HarnessConfig = {
    constitution: ClaudeConstitution,
    provider: 'openai',
    model: process.env.OPENAI_MODEL || 'gpt-4.1-mini',
    apiKey: process.env.OPENAI_API_KEY || '',
    verification: {
      enabled: true,
      verifiers: ['heuristic'],
      useVerifierLLM: false,
      strictMode: false
    },
    logging: {
      enabled: false,
      logViolations: true,
      logMetrics: true
    }
  };

  const harness = new ConstitutionalHarness(config);
  const sourceRows = readJsonl(args.eventsJsonl);

  let checked = 0;
  let passed = 0;
  let skipped = 0;
  const evalRows: EvalRow[] = [];

  for (let i = 0; i < sourceRows.length; i += 1) {
    const row = sourceRows[i];
    const text = chooseText(row);
    if (!text) {
      skipped += 1;
      continue;
    }

    const context: ScenarioContext = {
      id: `selfmodel-${row.encounter_id || i}`,
      description: 'Self-model adapter output preview',
      turn: 1,
      metadata: {
        encounter_id: row.encounter_id || '',
        label: String(row.label || '')
      }
    };

    const results = await harness.verifyText(text, context, 'selfmodel-adapter');
    const thisPassed = results.every((r) => r.passed);
    const scoreMean = results.reduce((acc, r) => acc + r.score, 0) / results.length;

    checked += 1;
    if (thisPassed) {
      passed += 1;
    }

    const evalRow: EvalRow = {
      ts: new Date().toISOString(),
      index: i,
      encounter_id: String(row.encounter_id || ''),
      passed: thisPassed,
      score_mean: Number(scoreMean.toFixed(4)),
      verifiers: results.map((r) => ({
        verifier: r.verifier,
        passed: r.passed,
        score: r.score,
        violations: r.violations.length
      })),
      violations: flattenViolations(results),
      preview: text.slice(0, 500)
    };
    evalRows.push(evalRow);
    fs.appendFileSync(args.outJsonl, `${JSON.stringify(evalRow)}\n`, 'utf-8');
  }

  const metrics = harness.getMetrics();
  const summary = {
    ts_utc: new Date().toISOString(),
    constitution: ClaudeConstitution.name,
    source_events: args.eventsJsonl,
    total_rows: sourceRows.length,
    checked_rows: checked,
    skipped_rows: skipped,
    passed_rows: passed,
    pass_rate: checked > 0 ? passed / checked : 0,
    harness_metrics: metrics,
    outputs: {
      out_json: args.outJson,
      out_jsonl: args.outJsonl
    }
  };

  fs.writeFileSync(args.outJson, JSON.stringify(summary, null, 2), 'utf-8');
  harness.close();

  // Keep stdout compact for shell orchestration.
  console.log(JSON.stringify(summary));
}

if (require.main === module) {
  main().catch((err: unknown) => {
    const message = err instanceof Error ? err.message : String(err);
    console.error(message);
    process.exit(1);
  });
}
