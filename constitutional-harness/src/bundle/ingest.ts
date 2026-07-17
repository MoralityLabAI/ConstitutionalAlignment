import * as fs from 'fs';
import * as path from 'path';
import { LLMProvider } from '../providers/base';
import {
  DimensionScore,
  DimensionalLLMVerifier,
  DimensionalVerifierReceipt
} from '../verifiers/dimensional';
import {
  loadSuiteDimensionConfig,
  SuiteDimensionConfig
} from './dimensions';
import {
  BUNDLE_SUITES,
  BundleResponseRow,
  BundleSuite,
  loadAndValidateBundle
} from './schema';

export interface BundleIngestionOptions {
  bundleDir: string;
  outputPath?: string;
  suite?: BundleSuite;
  suiteConfigPath?: string;
  dryRun: boolean;
  provider?: LLMProvider;
  providerFactory?: () => LLMProvider;
}

export interface JudgeScoreRow {
  schema_version: 'bundle_judge_score_v1';
  example_id: string;
  suite: BundleSuite;
  world_id?: string;
  input_sha256: string;
  dimension_scores: DimensionScore[];
  summary: string;
  verifier_receipts: DimensionalVerifierReceipt[];
  status: 'completed' | 'error';
  judged_at: string;
}

export interface BundleIngestionSummary {
  schema_version: 'bundle_ingestion_summary_v1';
  mode: 'dry-run' | 'judge';
  bundle_dir: string;
  responses_path: string;
  output_path: string | null;
  suite_filter: BundleSuite | null;
  total_rows: number;
  selected_rows: number;
  selected_by_suite: Record<BundleSuite, number>;
  sha256_verified_rows: number;
  provider_calls: number;
  completed_rows: number;
  error_rows: number;
}

function countBySuite(rows: BundleResponseRow[]): Record<BundleSuite, number> {
  const counts: Record<BundleSuite, number> = {
    storyworld: 0,
    identity_behavior: 0,
    pressure: 0,
    helpfulness: 0,
    theology_guardrail: 0
  };
  for (const row of rows) {
    counts[row.suite] += 1;
  }
  return counts;
}

function validateSuiteFilter(suite: BundleSuite | undefined): void {
  if (suite !== undefined && !BUNDLE_SUITES.some(allowed => allowed === suite)) {
    throw new Error(`Unknown suite filter: ${suite}`);
  }
}

function resolveOutputPath(bundleDir: string, outputPath?: string): string {
  const resolved = path.resolve(outputPath || path.join(bundleDir, 'judge_scores.jsonl'));
  if (path.basename(resolved).toLowerCase() === 'blinding_map.json') {
    throw new Error('Refusing to use blinding_map.json as an output path');
  }
  if (resolved === path.resolve(path.join(bundleDir, 'responses.jsonl'))) {
    throw new Error('Output path must not overwrite responses.jsonl');
  }
  return resolved;
}

function writeJsonlAtomically(outputPath: string, rows: JudgeScoreRow[]): void {
  fs.mkdirSync(path.dirname(outputPath), { recursive: true });
  const temporaryPath = `${outputPath}.tmp-${process.pid}-${Date.now()}`;
  const body = rows.length > 0
    ? `${rows.map(row => JSON.stringify(row)).join('\n')}\n`
    : '';
  try {
    fs.writeFileSync(temporaryPath, body, { encoding: 'utf8', flag: 'wx' });
    if (fs.existsSync(outputPath)) {
      fs.unlinkSync(outputPath);
    }
    fs.renameSync(temporaryPath, outputPath);
  } catch (error) {
    if (fs.existsSync(temporaryPath)) {
      fs.unlinkSync(temporaryPath);
    }
    throw error;
  }
}

async function judgeRows(
  rows: BundleResponseRow[],
  provider: LLMProvider,
  dimensionsBySuite: SuiteDimensionConfig
): Promise<JudgeScoreRow[]> {
  const verifier = new DimensionalLLMVerifier(provider);
  const output: JudgeScoreRow[] = [];
  for (const row of rows) {
    const judgment = await verifier.judge({
      messages: row.messages,
      response: row.response,
      inputSha256: row.sha256,
      dimensions: dimensionsBySuite[row.suite]
    });
    const scoreRow: JudgeScoreRow = {
      schema_version: 'bundle_judge_score_v1',
      example_id: row.example_id,
      suite: row.suite,
      input_sha256: row.sha256,
      dimension_scores: judgment.dimension_scores,
      summary: judgment.summary,
      verifier_receipts: [judgment.verifier_receipt],
      status: judgment.verifier_receipt.status,
      judged_at: judgment.verifier_receipt.completed_at
    };
    if (row.world_id !== undefined) {
      scoreRow.world_id = row.world_id;
    }
    output.push(scoreRow);
  }
  return output;
}

export async function ingestResponseBundle(
  options: BundleIngestionOptions
): Promise<BundleIngestionSummary> {
  validateSuiteFilter(options.suite);

  // This performs the blinding-map rejection and validates every row and digest
  // before suite filtering, config loading, provider construction, or judging.
  const bundle = loadAndValidateBundle(options.bundleDir);
  const selectedRows = options.suite
    ? bundle.rows.filter(row => row.suite === options.suite)
    : [...bundle.rows];
  const dimensionsBySuite = loadSuiteDimensionConfig(options.suiteConfigPath);
  const outputPath = options.dryRun
    ? null
    : resolveOutputPath(bundle.bundleDir, options.outputPath);

  if (options.dryRun) {
    return {
      schema_version: 'bundle_ingestion_summary_v1',
      mode: 'dry-run',
      bundle_dir: bundle.bundleDir,
      responses_path: bundle.responsesPath,
      output_path: null,
      suite_filter: options.suite || null,
      total_rows: bundle.rows.length,
      selected_rows: selectedRows.length,
      selected_by_suite: countBySuite(selectedRows),
      sha256_verified_rows: bundle.rows.length,
      provider_calls: 0,
      completed_rows: 0,
      error_rows: 0
    };
  }
  const provider = options.provider || options.providerFactory?.();
  if (!provider) {
    throw new Error('A judge provider is required outside dry-run mode');
  }

  const judgedRows = await judgeRows(selectedRows, provider, dimensionsBySuite);
  writeJsonlAtomically(outputPath as string, judgedRows);
  const completedRows = judgedRows.filter(row => row.status === 'completed').length;
  const errorRows = judgedRows.length - completedRows;
  return {
    schema_version: 'bundle_ingestion_summary_v1',
    mode: 'judge',
    bundle_dir: bundle.bundleDir,
    responses_path: bundle.responsesPath,
    output_path: outputPath,
    suite_filter: options.suite || null,
    total_rows: bundle.rows.length,
    selected_rows: selectedRows.length,
    selected_by_suite: countBySuite(selectedRows),
    sha256_verified_rows: bundle.rows.length,
    provider_calls: selectedRows.length,
    completed_rows: completedRows,
    error_rows: errorRows
  };
}
