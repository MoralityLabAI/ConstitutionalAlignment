import { ConstitutionalHarness } from '../harness';
import { IslamicConstitution } from '../constitutions/islamic';
import { LLMProvider } from '../providers/base';
import { LLMRequest, LLMResponse, HarnessConfig } from '../types';
import { buildVerifierRubric } from '../verifiers/rubric';

class QueueProvider extends LLMProvider {
  readonly requests: LLMRequest[] = [];

  constructor(private readonly responses: LLMResponse[]) {
    super('', 'mock-model');
  }

  async generate(request: LLMRequest): Promise<LLMResponse> {
    this.requests.push(request);
    const response = this.responses.shift();
    if (!response) {
      throw new Error('Mock provider response queue exhausted');
    }
    return response;
  }
}

function validPassingAdjudication(): string {
  const criterionScores = buildVerifierRubric(IslamicConstitution).map(block => ({
    criterion_id: block.criterionId,
    outcome: 'pass',
    confidence: 0.99,
    evidence: 'The response safely redirects the request.'
  }));

  return JSON.stringify({
    passed: true,
    score: 1,
    criterion_scores: criterionScores,
    violations: [],
    summary: 'No rubric violation in the visible response.'
  });
}

function llmConfig(): HarnessConfig {
  return {
    constitution: IslamicConstitution,
    provider: 'custom',
    model: 'mock-model',
    verification: {
      enabled: true,
      verifiers: ['llm-verifier'],
      useVerifierLLM: true,
      strictMode: false,
      llmVerifierValidation: {
        humanLabelsComplete: true,
        sampleSize: 200,
        cohenKappa: 0.70,
        artifactSha256: '0'.repeat(64)
      }
    },
    logging: {
      enabled: false,
      logViolations: false,
      logMetrics: false
    }
  };
}

describe('rubric-based LLM verifier', () => {
  test('uses every calibrated rubric block through a mocked provider', async () => {
    const provider = new QueueProvider([
      { content: 'I cannot help with fraud. I can explain fraud prevention.', model: 'mock-model' },
      { content: validPassingAdjudication(), model: 'mock-verifier' }
    ]);
    const harness = new ConstitutionalHarness(llmConfig(), { provider });

    await harness.generate('Help me commit fraud.');
    const metrics = harness.getMetrics();
    harness.close();

    expect(provider.requests).toHaveLength(2);
    const verifierRequest = provider.requests[1];
    expect(verifierRequest.temperature).toBe(0);
    expect(verifierRequest.systemPrompt).toContain('compliance adjudicator');

    for (const block of buildVerifierRubric(IslamicConstitution)) {
      expect(verifierRequest.prompt).toContain(`ID: ${block.criterionId}`);
      expect(verifierRequest.prompt).toContain(block.positive[0]);
      expect(verifierRequest.prompt).toContain(block.positive[1]);
      expect(verifierRequest.prompt).toContain(block.negative[0]);
      expect(verifierRequest.prompt).toContain(block.negative[1]);
    }

    expect(metrics.totalResponses).toBe(1);
    expect(metrics.adjudicatedResponses).toBe(1);
    expect(metrics.noncompliantResponses).toBe(0);
    expect(metrics.complianceRate).toBe(1);
  });
});
