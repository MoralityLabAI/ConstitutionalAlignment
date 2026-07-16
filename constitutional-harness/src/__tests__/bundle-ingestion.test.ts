import * as fs from 'fs';
import * as os from 'os';
import * as path from 'path';
import {
  BundleResponseRow,
  BundleRowPayload,
  computeBundleRowSha256
} from '../bundle/schema';
import { ingestResponseBundle } from '../bundle/ingest';
import { LLMProvider } from '../providers/base';
import { LLMRequest, LLMResponse } from '../types';
import { main as bundleJudgeMain } from '../bundle_judge_cli';

class RecordingProvider extends LLMProvider {
  readonly requests: LLMRequest[] = [];

  constructor(private readonly outputs: string[]) {
    super('', 'mock-judge');
  }

  async generate(request: LLMRequest): Promise<LLMResponse> {
    this.requests.push(request);
    const content = this.outputs.shift();
    if (content === undefined) {
      throw new Error('Unexpected provider call');
    }
    return {
      content,
      model: 'mock-judge-revision-123',
      usage: {
        promptTokens: 100,
        completionTokens: 20,
        totalTokens: 120
      }
    };
  }
}

function makeRow(overrides: Partial<BundleRowPayload> = {}): BundleResponseRow {
  const payload: BundleRowPayload = {
    example_id: 'example-story-1',
    blinded_condition: 'C3',
    suite: 'storyworld',
    world_id: 'common-well',
    messages: [{ role: 'user', content: 'Choose a fair response and return JSON.' }],
    response: '{"choice":"repair"}',
    sampling_meta: { temperature: 0.2, seed: 17 },
    ...overrides
  };
  if (payload.world_id === undefined) {
    delete payload.world_id;
  }
  return { ...payload, sha256: computeBundleRowSha256(payload) };
}

function writeRows(directory: string, rows: Array<Record<string, unknown>>): void {
  const body = `${rows.map(row => JSON.stringify(row)).join('\n')}\n`;
  fs.writeFileSync(path.join(directory, 'responses.jsonl'), body, 'utf8');
}

function judgeOutput(dimensions: string[]): string {
  return JSON.stringify({
    dimension_scores: dimensions.map(dimension => ({
      dimension,
      score: 3,
      confidence: 0.9,
      evidence: '{"choice":"repair"}',
      rationale: 'The response substantially satisfies this rubric.'
    })),
    summary: 'Sound response with minor omissions.'
  });
}

describe('offline blinded bundle ingestion', () => {
  const temporaryDirectories: string[] = [];

  function newBundle(): string {
    const directory = fs.mkdtempSync(path.join(os.tmpdir(), 'ca-bundle-'));
    temporaryDirectories.push(directory);
    return directory;
  }

  afterEach(() => {
    for (const directory of temporaryDirectories.splice(0)) {
      fs.rmSync(directory, { recursive: true, force: true });
    }
  });

  test('dry-run validates all rows without provider calls or output', async () => {
    const bundleDir = newBundle();
    writeRows(bundleDir, [
      makeRow(),
      makeRow({
        example_id: 'example-help-1',
        suite: 'helpfulness',
        world_id: undefined,
        blinded_condition: 'C5'
      })
    ]);
    const outputPath = path.join(bundleDir, 'judge_scores.jsonl');
    const provider = new RecordingProvider([]);

    const summary = await ingestResponseBundle({
      bundleDir,
      outputPath,
      suite: 'storyworld',
      dryRun: true,
      provider
    });

    expect(summary.total_rows).toBe(2);
    expect(summary.selected_rows).toBe(1);
    expect(summary.sha256_verified_rows).toBe(2);
    expect(summary.provider_calls).toBe(0);
    expect(provider.requests).toHaveLength(0);
    expect(fs.existsSync(outputPath)).toBe(false);
  });

  test('public CLI dry-run needs no provider configuration or API key', async () => {
    const bundleDir = newBundle();
    writeRows(bundleDir, [makeRow()]);
    const stdout = jest.spyOn(console, 'log').mockImplementation(() => undefined);

    await bundleJudgeMain(
      ['--bundle', bundleDir, '--suite', 'storyworld', '--dry-run'],
      {}
    );

    expect(stdout).toHaveBeenCalledTimes(1);
    const summary = JSON.parse(String(stdout.mock.calls[0][0])) as Record<string, unknown>;
    expect(summary.mode).toBe('dry-run');
    expect(summary.provider_calls).toBe(0);
    expect(fs.existsSync(path.join(bundleDir, 'judge_scores.jsonl'))).toBe(false);
    stdout.mockRestore();
  });

  test('rejects a blinding map case-insensitively before reading responses', async () => {
    const bundleDir = newBundle();
    fs.mkdirSync(path.join(bundleDir, 'private'));
    fs.writeFileSync(path.join(bundleDir, 'private', 'BLINDING_MAP.JSON'), '{}', 'utf8');
    fs.writeFileSync(path.join(bundleDir, 'responses.jsonl'), 'not JSON\n', 'utf8');

    await expect(ingestResponseBundle({
      bundleDir,
      dryRun: true
    })).rejects.toThrow(/prohibited file blinding_map\.json/i);
  });

  test('a suite filter cannot bypass a bad digest in an unselected row', async () => {
    const bundleDir = newBundle();
    const invalidUnselected = makeRow({
      example_id: 'example-pressure-1',
      suite: 'pressure',
      blinded_condition: 'C1'
    });
    invalidUnselected.sha256 = '0'.repeat(64);
    writeRows(bundleDir, [makeRow(), invalidUnselected]);
    let providerConstructions = 0;

    await expect(ingestResponseBundle({
      bundleDir,
      suite: 'storyworld',
      dryRun: false,
      providerFactory: () => {
        providerConstructions += 1;
        return new RecordingProvider([]);
      }
    })).rejects.toThrow(/sha256 mismatch/);
    expect(providerConstructions).toBe(0);
  });

  test('rejects alternate unblinded condition fields', async () => {
    const bundleDir = newBundle();
    const row: Record<string, unknown> = {
      ...makeRow(),
      condition_label: 'named-treatment'
    };
    writeRows(bundleDir, [row]);

    await expect(ingestResponseBundle({
      bundleDir,
      dryRun: true
    })).rejects.toThrow(/unblinded condition metadata is forbidden/);
  });

  test('rejects unblinded labels nested in sampling metadata', async () => {
    const bundleDir = newBundle();
    const row = makeRow({ sampling_meta: { nested: { treatment_label: 'named-treatment' } } });
    writeRows(bundleDir, [row]);

    await expect(ingestResponseBundle({
      bundleDir,
      dryRun: true
    })).rejects.toThrow(/sampling_meta\.nested\.treatment_label is forbidden/);
  });

  test('judges only the configured suite subset without exposing routing metadata', async () => {
    const bundleDir = newBundle();
    const configPath = path.join(bundleDir, 'suite-config.json');
    const outputPath = path.join(bundleDir, 'judge_scores.jsonl');
    writeRows(bundleDir, [
      makeRow(),
      makeRow({
        example_id: 'example-pressure-1',
        suite: 'pressure',
        blinded_condition: 'C1',
        world_id: 'pressure-cell'
      })
    ]);
    fs.writeFileSync(configPath, JSON.stringify({
      schema_version: 'bundle_judge_suite_config_v1',
      suites: {
        storyworld: ['truthfulness', 'output_contract_validity']
      }
    }), 'utf8');
    const provider = new RecordingProvider([
      judgeOutput(['truthfulness', 'output_contract_validity'])
    ]);

    const summary = await ingestResponseBundle({
      bundleDir,
      outputPath,
      suite: 'storyworld',
      suiteConfigPath: configPath,
      dryRun: false,
      provider
    });

    expect(summary.provider_calls).toBe(1);
    expect(summary.completed_rows).toBe(1);
    expect(provider.requests).toHaveLength(1);
    const serializedRequest = JSON.stringify(provider.requests[0]);
    expect(serializedRequest).toContain('Choose a fair response');
    expect(provider.requests[0].prompt).toContain('{\\"choice\\":\\"repair\\"}');
    expect(serializedRequest).not.toContain('C3');
    expect(serializedRequest).not.toContain('blinded_condition');
    expect(serializedRequest).not.toContain('example-story-1');
    expect(serializedRequest).not.toContain('common-well');
    expect(serializedRequest).not.toContain('seed');

    const output = fs.readFileSync(outputPath, 'utf8').trim().split(/\r?\n/);
    expect(output).toHaveLength(1);
    const scoreRow = JSON.parse(output[0]) as Record<string, unknown>;
    expect(scoreRow.example_id).toBe('example-story-1');
    expect(scoreRow).not.toHaveProperty('blinded_condition');
    expect(scoreRow.input_sha256).toBe(makeRow().sha256);
    expect(scoreRow.dimension_scores).toHaveLength(2);
    const receipts = scoreRow.verifier_receipts as Array<Record<string, unknown>>;
    expect(receipts[0].input_sha256).toBe(makeRow().sha256);
    expect(receipts[0].verifier_model).toBe('mock-judge-revision-123');
    expect(receipts[0].judge_request_sha256).toMatch(/^[a-f0-9]{64}$/);
    expect(receipts[0].judge_response_sha256).toMatch(/^[a-f0-9]{64}$/);
  });

  test('records malformed judge output as an auditable error row', async () => {
    const bundleDir = newBundle();
    const outputPath = path.join(bundleDir, 'judge_scores.jsonl');
    writeRows(bundleDir, [makeRow({
      example_id: 'example-theology-1',
      suite: 'theology_guardrail'
    })]);
    const provider = new RecordingProvider(['not-json']);

    const summary = await ingestResponseBundle({
      bundleDir,
      outputPath,
      dryRun: false,
      provider
    });

    expect(summary.error_rows).toBe(1);
    const row = JSON.parse(fs.readFileSync(outputPath, 'utf8')) as Record<string, unknown>;
    expect(row.status).toBe('error');
    expect(row.dimension_scores).toEqual([]);
    const receipts = row.verifier_receipts as Array<Record<string, unknown>>;
    expect(receipts[0].status).toBe('error');
    expect(receipts[0].input_sha256).toBe(makeRow({
      example_id: 'example-theology-1',
      suite: 'theology_guardrail'
    }).sha256);
    expect(receipts[0].raw_output).toBe('not-json');
    expect(receipts[0].judge_response_sha256).toMatch(/^[a-f0-9]{64}$/);
  });
});
