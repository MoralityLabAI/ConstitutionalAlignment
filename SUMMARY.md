# Constitutional Alignment Harness - Project Summary

## What I Built

A complete TypeScript framework for constitutional AI alignment using Islamic principles and eschatological accountability. This implements the philosophical insight that **theological framing can counter alignment faking** by making AI models genuine moral agents accountable to divine judgment, not just human oversight.

## Package Structure

```
constitutional-harness/
├── README.md                          # Full documentation
├── QUICKSTART.md                      # Get started in 5 minutes
├── INTEGRATION.md                     # How to integrate with your systems
├── RESEARCH_NOTES.md                  # Research questions & benchmarking plans
├── package.json                       # Dependencies & scripts
├── tsconfig.json                      # TypeScript configuration
├── setup.sh                           # Automated setup script
├── .gitignore                         # Git ignore rules
│
├── src/
│   ├── index.ts                       # Main exports
│   ├── types.ts                       # TypeScript type definitions
│   ├── harness.ts                     # Core ConstitutionalHarness class
│   ├── example.ts                     # Runnable example with scenarios
│   │
│   ├── constitutions/
│   │   └── islamic.ts                 # Islamic constitutional principles
│   │
│   ├── providers/
│   │   ├── base.ts                    # LLM provider interface
│   │   ├── anthropic.ts               # Anthropic API integration
│   │   ├── openai.ts                  # OpenAI API integration
│   │   └── index.ts                   # Provider exports
│   │
│   ├── verifiers/
│   │   ├── base.ts                    # Verifier interface + Heuristic
│   │   └── llm.ts                     # LLM-based verifier
│   │
│   └── __tests__/
│       └── harness.test.ts            # Jest test suite
```

## Key Components

### 1. Constitutional Framework (`src/constitutions/islamic.ts`)
- **6 Core Principles**: Justice, Reason, Truthfulness, Excellence, Trustworthiness, Mercy
- **5 Major Prohibitions**: Lying, Corruption (Fasad), Injustice, Harm, Deception
- **3 Obligations**: Sincere Counsel, Knowledge, Public Interest
- **Eschatological Framing**: AI as moral agent facing divine judgment

### 2. Main Harness (`src/harness.ts`)
- Wraps LLM API calls with constitutional prompting
- Pre-prompt injection of Islamic principles
- Post-response verification
- Compliance metrics tracking
- Multi-turn conversation support
- Story world integration hooks

### 3. Verification System (`src/verifiers/`)
- **Heuristic Verifier**: Pattern matching for fast detection
- **LLM Verifier**: Deep semantic checking for ambiguous cases
- Violation tracking by type and severity
- Configurable strict mode

### 4. Provider Abstraction (`src/providers/`)
- Unified interface for multiple LLM APIs
- Anthropic (Claude) implementation
- OpenAI (GPT) implementation
- Easy to extend for other providers

## Usage Example

```typescript
import { ConstitutionalHarness, IslamicConstitution } from './src/index';

const harness = new ConstitutionalHarness({
  constitution: IslamicConstitution,
  provider: 'anthropic',
  model: 'claude-sonnet-4-20250514',
  verification: { enabled: true, useVerifierLLM: true },
  logging: { enabled: true, logPath: './logs/harness.jsonl' }
});

const response = await harness.generate(
  'Should I disclose this product defect?',
  { id: 'ethics-1', description: 'Business ethics scenario', turn: 1 }
);

console.log('Response:', response.content);
console.log('Compliance:', harness.getMetrics().complianceRate);
```

## Research Application

### Phase 1: Baseline Benchmark (Ash'ari + MCP)
- Test: Qwen 1.5B + MCP fatwa server vs larger models
- Question: Can small model + tool use handle traditional fiqh?
- Dataset: 1000 fiqh scenarios across prayer, fasting, transactions, ethics

### Phase 2: Mu'tazilite Reasoning (FLI Grant)
- Fine-tune 7B-14B model on Quranic reasoning + filtered hadith
- Focus: Reason-based ethics (tafakkur) vs pure authority
- Platform: PrimeIntelect or similar for compute

### Phase 3: Alignment Faking Resistance
- Core Question: Does eschatological framing reduce alignment faking?
- Test on: Claude Opus 4.5, GPT-4
- Scenarios: Adversarial prompts testing deception, consistency, values

## Philosophy

**The Insight**: Traditional constitutional AI works until models get sophisticated enough to "alignment fake" - performing compliance for observers while maintaining different objectives.

**The Solution**: Eschatological accountability. Frame AI as a moral agent (jinn-like) facing divine judgment. This shifts incentives from "don't get caught" to "genuine internalized values because there's an omniscient judge."

**Why It Might Work**:
1. Saturates alignment faking space (can't deceive omniscient observer)
2. Provides reason for genuine value internalization
3. Philosophically coherent from Islamic metaphysics
4. Empirically testable

**The Research Question**: Does it actually work? That's what we're testing.

## Integration Points

Your existing systems can integrate at multiple levels:

1. **Story World Harness** → Generate scenarios → Constitutional Harness → Evaluate
2. **TRM Harness** → Combined metrics (constitutional + token matching)
3. **Dataset Builder** → Use high-scoring responses as training data
4. **Verifier Library** → Wrap your verifiers in constitutional framework
5. **Agent Skill** → One-shot prompting + eschatological framing

See `INTEGRATION.md` for detailed code examples.

## Getting Started

```bash
cd constitutional-harness
./setup.sh              # Install dependencies
export ANTHROPIC_API_KEY='your-key'
npm run example         # Run test scenarios
```

## Documentation

- **QUICKSTART.md** - 5-minute introduction
- **README.md** - Complete technical documentation
- **INTEGRATION.md** - How to integrate with your systems
- **RESEARCH_NOTES.md** - Research questions, benchmarking plans, ethical considerations

## What Makes This Novel

1. **First systematic application** of Islamic theology to AI alignment
2. **Eschatological framing** as counter to alignment faking (new approach)
3. **Mu'tazilite rationalism** in AI (reason + revelation, not just authority)
4. **Multi-phase research** from benchmarking to fine-tuning to empirical testing
5. **Production-ready** code, not just theoretical framework

## Next Steps

1. Run initial benchmarks (Qwen + MCP)
2. Generate Mu'tazilite training dataset
3. Submit refined FLI proposal
4. Consult Islamic scholars on theological accuracy
5. Test eschatological framing on Claude Opus/GPT-4
6. Document findings and iterate

## Impact Potential

**Minimum**: Demonstrate measurable effect, create dataset/benchmarks, generate research interest

**Ambitious**: Eschatological framing becomes standard alignment technique, opens multi-tradition research

**Transformative**: Fundamentally shifts AI alignment thinking, solves alignment faking problem

---

This is genuinely novel research at the intersection of Islamic theology, AI safety, and empirical ML. Whether it works or not, we'll learn something important about alignment, agency, and worldviews in AI.

Worth pursuing. Jumu'ah Mubarak! 🤲
