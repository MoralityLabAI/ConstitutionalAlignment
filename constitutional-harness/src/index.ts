/**
 * Constitutional Alignment Harness
 * 
 * A framework for aligning LLM behavior with Islamic constitutional principles,
 * emphasizing eschatological accountability and moral agency.
 */

export { ConstitutionalHarness } from './harness';
export { IslamicConstitution, ConstitutionalPrinciples } from './constitutions/islamic';
export { ClaudeConstitution } from './constitutions/claude';
export { VerificationResult, Verifier } from './verifiers/base';
export { LLMProvider, AnthropicProvider, OpenAIProvider } from './providers';
export type { 
  HarnessConfig, 
  ConstitutionConfig,
  ScenarioContext,
  ComplianceMetrics 
} from './types';
