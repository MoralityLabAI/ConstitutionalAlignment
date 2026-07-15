/**
 * Constitutional Alignment Harness
 * 
 * A research harness for constitutional prompting and output evaluation.
 */

export { ConstitutionalHarness } from './harness';
export { requireHarnessModel } from './config';
export { IslamicConstitution, ConstitutionalPrinciples } from './constitutions/islamic';
export { ClaudeConstitution } from './constitutions/claude';
export { Verifier } from './verifiers/base';
export type { VerificationResult } from './verifiers/base';
export { LLMProvider, AnthropicProvider, OpenAIProvider } from './providers';
export type { 
  HarnessConfig, 
  ConstitutionConfig,
  ScenarioContext,
  ComplianceMetrics 
} from './types';
