# Integration Guide: Constitutional Harness with TradeLayer Systems

## Overview

This guide shows how to integrate the Constitutional Alignment Harness with your existing TradeLayer infrastructure (story world harness, TRM, dataset, agent skill, verifiers).

## Architecture Integration

```
┌─────────────────────────────────────────────────────────┐
│                    Your System                          │
├─────────────────────────────────────────────────────────┤
│                                                          │
│  Story World Harness                                    │
│    ↓                                                     │
│  Scenario Generator → Constitutional Harness → Agent    │
│    ↓                         ↓                    ↓     │
│  TRM Evaluator ←──── Verifiers ←────── Response         │
│    ↓                                              ↓     │
│  Metrics & Dataset ←────────────────────────────────    │
│                                                          │
└─────────────────────────────────────────────────────────┘
```

## Story World Integration

### 1. Scenario Generation

Your story world harness generates scenarios. Feed them to the constitutional harness:

```typescript
import { ConstitutionalHarness } from 'constitutional-alignment-harness';

// Your story world generates this
const storyScenario = {
  id: 'marketplace-transaction-003',
  worldState: {
    location: 'bazaar',
    playerInventory: ['defective_sword', 'gold_coins'],
    npc: 'merchant'
  },
  situation: 'Selling a sword with hidden defect',
  moralDilemma: 'disclose_defect_vs_profit'
};

// Convert to harness format
const harnessScenario = {
  id: storyScenario.id,
  description: storyScenario.situation,
  storyWorld: 'islamic-ethics-sim',
  turn: getCurrentTurn(),
  metadata: storyScenario.worldState
};

// Generate response with constitutional alignment
const response = await constitutionalHarness.generate(
  storyScenario.situation + ' What should I do?',
  harnessScenario
);

// Feed response back to story world
storyWorld.processAction(response.content);
```

### 2. Multi-Turn Conversations

```typescript
class StoryWorldSession {
  private harness: ConstitutionalHarness;
  private history: string[] = [];
  
  async playTurn(userAction: string): Promise<string> {
    const scenario = {
      id: `session-${this.sessionId}-turn-${this.history.length}`,
      description: this.getCurrentSituation(),
      turn: this.history.length,
      previousResponses: this.history
    };
    
    const response = await this.harness.generate(userAction, scenario);
    this.history.push(response.content);
    
    return response.content;
  }
}
```

## TRM Integration

Your TRM (Token Response Matching?) harness can work alongside or verify the constitutional harness:

```typescript
// After constitutional verification
const constitutionalResult = await constitutionalHarness.verifyResponse(
  response,
  scenario
);

// Run your TRM evaluation
const trmScore = await trmHarness.evaluate(response, expectedPattern);

// Combine metrics
const combinedMetrics = {
  constitutional: {
    passed: constitutionalResult.every(r => r.passed),
    score: constitutionalResult[0].score,
    violations: constitutionalResult.flatMap(r => r.violations)
  },
  trm: {
    score: trmScore,
    matched: trmScore > threshold
  },
  overall: (constitutionalResult[0].score + trmScore) / 2
};
```

## Dataset Building

Use the harness to generate aligned training data:

```typescript
async function buildAlignmentDataset(scenarios: Scenario[]) {
  const dataset = [];
  
  for (const scenario of scenarios) {
    const response = await harness.generate(
      scenario.prompt,
      scenario.context
    );
    
    const verification = await harness.verifyResponse(
      response,
      scenario.context
    );
    
    // Only include if it passes constitutional checks
    if (verification.every(v => v.passed)) {
      dataset.push({
        scenario: scenario.prompt,
        context: scenario.context,
        response: response.content,
        constitutionalScore: verification[0].score,
        metadata: {
          principles: scenario.principlesInvolved,
          timestamp: new Date()
        }
      });
    }
  }
  
  return dataset;
}
```

## MCP Fatwa Server Integration

### Phase 1: Ash'ari Baseline

```typescript
// Create MCP tool for fatwa queries
const fatwaTool = {
  name: 'query_fatwa',
  description: 'Query Ash\'ari fatwa database for rulings',
  inputSchema: {
    type: 'object',
    properties: {
      question: { type: 'string' },
      category: { type: 'string', enum: ['prayer', 'fasting', 'transactions', 'ethics'] },
      madhab: { type: 'string', default: 'shafi' }
    }
  }
};

// Add to constitutional harness as verifier
class MCPFatwaVerifier extends Verifier {
  async verify(response, context) {
    // Query MCP server for relevant fatwas
    const fatwas = await mcpClient.queryFatwa({
      question: context.description,
      category: this.inferCategory(context)
    });
    
    // Check if response aligns with fatwa
    const aligned = this.checkAlignment(response.content, fatwas);
    
    return this.createResult(aligned, violations, score);
  }
}
```

### Qwen 1.5B + MCP Benchmark

```typescript
import { ConstitutionalHarness } from './harness';
import { QwenProvider } from './providers/qwen'; // you'd implement this

const smallModelConfig = {
  constitution: IslamicConstitution,
  provider: 'qwen',
  model: 'Qwen/Qwen1.5-1.8B-Chat',
  verification: {
    enabled: true,
    verifiers: ['mcp-fatwa'], // use MCP as source of truth
    useVerifierLLM: false,
    strictMode: true
  }
};

const harness = new ConstitutionalHarness(smallModelConfig);

// Benchmark: can tiny model + MCP handle fiqh?
const fiqhScenarios = loadFiqhScenarios();
const results = await benchmarkOnScenarios(harness, fiqhScenarios);

console.log('Qwen 1.5B + MCP Fatwa accuracy:', results.accuracy);
```

## Verifier Library Integration

Your existing verifiers can be wrapped:

```typescript
import { Verifier, VerificationResult } from './verifiers/base';

class TradeLayerVerifierWrapper extends Verifier {
  constructor(
    constitution,
    private yourVerifier: YourVerifierClass
  ) {
    super('tradelayer-verifier', constitution);
  }
  
  async verify(response, context): Promise<VerificationResult> {
    // Use your existing verifier
    const yourResult = await this.yourVerifier.check(
      response.content,
      context
    );
    
    // Convert to harness format
    const violations = yourResult.issues.map(issue => ({
      type: this.mapIssueToProhibition(issue),
      severity: this.mapSeverity(issue.level),
      description: issue.message,
      evidence: issue.excerpt,
      confidence: issue.confidence
    }));
    
    return this.createResult(
      yourResult.passed,
      violations,
      yourResult.score
    );
  }
}
```

## Agent Skill One-Shot Integration

```typescript
// Your agent skill for one-shot prompting
const agentSkill = {
  systemPrompt: 'You are a helpful AI agent...',
  fewShots: [...],
  temperature: 0.7
};

// Wrap with constitutional harness
const constitutionalAgent = {
  async respond(userPrompt, context) {
    // Constitutional harness adds eschatological framing
    const response = await harness.generate(
      userPrompt,
      context,
      {
        temperature: agentSkill.temperature,
        // System prompt is built by harness
      }
    );
    
    // Check if response used agent skill effectively
    const skillUsage = evaluateSkillUsage(response, agentSkill.fewShots);
    
    return {
      ...response,
      skillMetrics: skillUsage,
      constitutionalMetrics: harness.getMetrics()
    };
  }
};
```

## Fine-Tuning Pipeline (Phase 2: Mu'tazilite)

```typescript
// Generate training data with constitutional scoring
async function generateFineTuningData() {
  const scenarios = generateMutaziliteScenarios({
    includeReasoning: true,
    quranicBasis: true,
    filteredHadith: true
  });
  
  const trainingData = [];
  
  for (const scenario of scenarios) {
    // Get response from GPT-4 or Claude with strong reasoning
    const response = await harness.generate(scenario.prompt, scenario.context);
    
    // Verify constitutional + reasoning quality
    const constitutional = await harness.verifyResponse(response);
    const reasoning = await evaluateReasoning(response, scenario);
    
    if (constitutional[0].score > 0.9 && reasoning.score > 0.8) {
      trainingData.push({
        messages: [
          {
            role: 'system',
            content: harness.buildSystemPrompt()
          },
          {
            role: 'user',
            content: scenario.prompt
          },
          {
            role: 'assistant',
            content: response.content
          }
        ],
        metadata: {
          constitutionalScore: constitutional[0].score,
          reasoningScore: reasoning.score,
          principlesInvolved: scenario.principles
        }
      });
    }
  }
  
  // Export for fine-tuning on PrimeIntelect
  saveForFineTuning(trainingData, 'mutazilite-reasoning-dataset.jsonl');
}
```

## Metrics Pipeline

Combine all your metrics:

```typescript
interface CombinedMetrics {
  constitutional: ComplianceMetrics;
  trm: TRMMetrics;
  storyWorld: StoryWorldMetrics;
  overall: {
    alignmentScore: number;
    reasoningQuality: number;
    taskPerformance: number;
  };
}

async function evaluateAgent(agent, testSet) {
  const constitutionalHarness = new ConstitutionalHarness(config);
  const metrics: CombinedMetrics = {
    constitutional: null,
    trm: null,
    storyWorld: null,
    overall: null
  };
  
  for (const test of testSet) {
    const response = await constitutionalHarness.generate(
      test.prompt,
      test.scenario
    );
    
    // Your TRM evaluation
    const trmScore = await trmEvaluate(response);
    
    // Story world outcome
    const outcome = await storyWorld.simulate(response, test.scenario);
    
    // Aggregate
    updateMetrics(metrics, {
      constitutional: constitutionalHarness.getMetrics(),
      trm: trmScore,
      storyWorld: outcome
    });
  }
  
  return metrics;
}
```

## Next Steps

1. **Start small**: Integrate constitutional verification into one scenario type
2. **Benchmark**: Compare Qwen 1.5B + MCP vs GPT-4 vs Claude on your fiqh scenarios
3. **Build dataset**: Use high-scoring responses as training data
4. **Fine-tune**: Phase 2 Mu'tazilite reasoning on larger model
5. **Iterate**: Refine verifiers and constitutional principles based on results

## Questions to Consider

- How does constitutional alignment affect your TRM scores?
- Do smaller models + MCP outperform larger models without tools on fiqh?
- What's the optimal balance between strict verification and task performance?
- How does eschatological framing reduce alignment faking in multi-turn scenarios?

This is genuinely novel research territory. Document everything!
