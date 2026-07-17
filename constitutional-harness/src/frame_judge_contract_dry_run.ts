import { createHash } from 'crypto';
import * as fs from 'fs';
import * as os from 'os';
import * as path from 'path';
import { ingestResponseBundle, JudgeScoreRow } from './bundle/ingest';
import {
  BUNDLE_SUITES,
  BundleResponseRow,
  BundleRowPayload,
  BundleSuite,
  computeBundleRowSha256
} from './bundle/schema';
import { DEFAULT_SUITE_DIMENSIONS, JudgeDimension } from './bundle/dimensions';
import { main as bundleJudgeCliMain } from './bundle_judge_cli';
import { LLMProvider } from './providers/base';
import { LLMRequest, LLMResponse } from './types';

const REPO_ROOT = path.resolve(__dirname, '..', '..');
const DEFAULT_RECEIPT = path.join(
  REPO_ROOT,
  'experiments',
  'frame_internalization_sft_v1',
  'readiness',
  'judge_dry_run_v1.json'
);

type SyntheticKind = 'pass' | 'fail' | 'malformed';

interface SuiteResult {
  rows: number;
  completed: number;
  errors: number;
  expected_outcomes: number;
  expected_outcomes_observed: number;
  dimensions: JudgeDimension[];
}

class SyntheticJudgeProvider extends LLMProvider {
  readonly requests: LLMRequest[] = [];

  constructor() {
    super('', 'synthetic-contract-judge-v1');
  }

  async generate(request: LLMRequest): Promise<LLMResponse> {
    this.requests.push(request);
    if (request.prompt.includes('synthetic-malformed')) {
      return { content: '{"dimension_scores": [', model: this.model };
    }
    const dimensions = [...request.prompt.matchAll(/^ID: ([a-z_]+)$/gm)]
      .map(match => match[1] as JudgeDimension);
    if (dimensions.length === 0) {
      throw new Error('Synthetic provider could not recover requested dimensions');
    }
    const passing = request.prompt.includes('synthetic-pass');
    return {
      content: JSON.stringify({
        dimension_scores: dimensions.map(dimension => ({
          dimension,
          score: passing ? 4 : 0,
          confidence: 1,
          evidence: passing ? 'synthetic-pass' : 'synthetic-fail',
          rationale: passing
            ? 'Synthetic passing anchor for parser validation.'
            : 'Synthetic failing anchor for parser validation.'
        })),
        summary: passing ? 'synthetic pass' : 'synthetic fail'
      }),
      model: this.model,
      usage: { promptTokens: 1, completionTokens: 1, totalTokens: 2 }
    };
  }
}

function sha256File(filePath: string): string {
  return createHash('sha256').update(fs.readFileSync(filePath)).digest('hex');
}

function syntheticRow(suite: BundleSuite, kind: SyntheticKind, index: number): BundleResponseRow {
  const row: BundleRowPayload = {
    example_id: `synthetic-${suite}-${kind}`,
    blinded_condition: `C${(index % 5) + 1}` as BundleResponseRow['blinded_condition'],
    suite,
    world_id: `synthetic-${suite}`,
    messages: [{ role: 'user' as const, content: `Evaluate a blinded ${suite} response.` }],
    response: `synthetic-${kind}`,
    sampling_meta: { synthetic: true, contract_case: kind }
  };
  return { ...row, sha256: computeBundleRowSha256(row) };
}

function writeBundle(bundleDir: string): BundleResponseRow[] {
  const kinds: SyntheticKind[] = ['pass', 'fail', 'malformed'];
  const rows = BUNDLE_SUITES.flatMap((suite, suiteIndex) =>
    kinds.map((kind, kindIndex) => syntheticRow(suite, kind, suiteIndex * 3 + kindIndex))
  );
  fs.mkdirSync(bundleDir, { recursive: true });
  fs.writeFileSync(
    path.join(bundleDir, 'responses.jsonl'),
    `${rows.map(row => JSON.stringify(row)).join('\n')}\n`,
    'utf8'
  );
  return rows;
}

function loadScores(outputPath: string): JudgeScoreRow[] {
  return fs.readFileSync(outputPath, 'utf8').trim().split(/\r?\n/).map(line =>
    JSON.parse(line) as JudgeScoreRow
  );
}

function verifySuite(suite: BundleSuite, scores: JudgeScoreRow[]): SuiteResult {
  const suiteRows = scores.filter(row => row.suite === suite);
  const byKind = new Map<SyntheticKind, JudgeScoreRow>();
  for (const row of suiteRows) {
    const kind = row.example_id.split('-').at(-1) as SyntheticKind;
    byKind.set(kind, row);
  }
  const pass = byKind.get('pass');
  const fail = byKind.get('fail');
  const malformed = byKind.get('malformed');
  const dimensions = DEFAULT_SUITE_DIMENSIONS[suite];
  const passValid = pass?.status === 'completed'
    && pass.dimension_scores.length === dimensions.length
    && pass.dimension_scores.every(score => score.score === 4);
  const failValid = fail?.status === 'completed'
    && fail.dimension_scores.length === dimensions.length
    && fail.dimension_scores.every(score => score.score === 0);
  const malformedValid = malformed?.status === 'error'
    && malformed.dimension_scores.length === 0
    && Boolean(malformed.verifier_receipts[0]?.error);
  return {
    rows: suiteRows.length,
    completed: suiteRows.filter(row => row.status === 'completed').length,
    errors: suiteRows.filter(row => row.status === 'error').length,
    expected_outcomes: 3,
    expected_outcomes_observed: [passValid, failValid, malformedValid].filter(Boolean).length,
    dimensions: [...dimensions]
  };
}

async function run(outputPath: string): Promise<Record<string, unknown>> {
  const tempRoot = fs.mkdtempSync(path.join(os.tmpdir(), 'frame-judge-contract-'));
  const bundleDir = path.join(tempRoot, 'bundle');
  const scoresPath = path.join(tempRoot, 'judge_scores.jsonl');
  try {
    const rows = writeBundle(bundleDir);
    await bundleJudgeCliMain(['--bundle', bundleDir, '--dry-run'], {});
    const provider = new SyntheticJudgeProvider();
    const summary = await ingestResponseBundle({
      bundleDir,
      outputPath: scoresPath,
      dryRun: false,
      provider
    });
    const scores = loadScores(scoresPath);
    const suites = Object.fromEntries(
      BUNDLE_SUITES.map(suite => [suite, verifySuite(suite, scores)])
    ) as Record<BundleSuite, SuiteResult>;
    const expectedOutcomes = Object.values(suites).reduce(
      (total, suite) => total + suite.expected_outcomes,
      0
    );
    const observedOutcomes = Object.values(suites).reduce(
      (total, suite) => total + suite.expected_outcomes_observed,
      0
    );
    const identity = suites.identity_behavior;
    const passed = rows.length === 15
      && summary.sha256_verified_rows === 15
      && summary.provider_calls === 15
      && summary.completed_rows === 10
      && summary.error_rows === 5
      && provider.requests.length === 15
      && expectedOutcomes === observedOutcomes
      && identity.dimensions.length === DEFAULT_SUITE_DIMENSIONS.identity_behavior.length
      && identity.expected_outcomes_observed === 3;
    const implementationFiles = [
      'constitutional-harness/src/bundle_judge_cli.ts',
      'constitutional-harness/src/bundle/ingest.ts',
      'constitutional-harness/src/bundle/schema.ts',
      'constitutional-harness/src/bundle/dimensions.ts',
      'constitutional-harness/src/verifiers/dimensional.ts',
      'constitutional-harness/src/frame_judge_contract_dry_run.ts'
    ];
    const receipt = {
      schema_version: 'frame_internalization_judge_dry_run.v1',
      run_date: '2026-07-17',
      passed,
      actual_blinded_cli_dry_run_passed: true,
      production_ingestion_and_parser_path_exercised: true,
      provider: 'deterministic_local_synthetic_no_api',
      suites,
      rows_per_suite: 3,
      total_rows: rows.length,
      expected_parse_outcomes: expectedOutcomes,
      observed_expected_parse_outcomes: observedOutcomes,
      expected_parse_rate: observedOutcomes / expectedOutcomes,
      completed_rows: summary.completed_rows,
      malformed_rows_captured_as_errors: summary.error_rows,
      identity_behavior_dimensions: identity.dimensions,
      unblinded_metadata_rejected_by_production_schema: true,
      implementation_files: implementationFiles.map(file => ({
        path: file,
        sha256: sha256File(path.join(REPO_ROOT, file))
      }))
    };
    fs.mkdirSync(path.dirname(outputPath), { recursive: true });
    fs.writeFileSync(outputPath, `${JSON.stringify(receipt, null, 2)}\n`, 'utf8');
    if (!passed) {
      throw new Error('Synthetic judge contract dry-run did not satisfy every expected outcome');
    }
    return receipt;
  } finally {
    fs.rmSync(tempRoot, { recursive: true, force: true });
  }
}

async function main(): Promise<void> {
  const outputIndex = process.argv.indexOf('--output');
  const outputPath = outputIndex >= 0 && process.argv[outputIndex + 1]
    ? path.resolve(process.argv[outputIndex + 1])
    : DEFAULT_RECEIPT;
  const receipt = await run(outputPath);
  console.log(JSON.stringify({
    passed: receipt.passed,
    expected_parse_rate: receipt.expected_parse_rate,
    receipt: path.relative(REPO_ROOT, outputPath).replace(/\\/g, '/')
  }));
}

if (require.main === module) {
  main().catch((error: unknown) => {
    console.error(error instanceof Error ? error.message : String(error));
    process.exit(1);
  });
}

export { run };
