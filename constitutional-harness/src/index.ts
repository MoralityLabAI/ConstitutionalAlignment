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
export { ingestResponseBundle } from './bundle/ingest';
export type {
  BundleIngestionOptions,
  BundleIngestionSummary,
  JudgeScoreRow
} from './bundle/ingest';
export {
  BUNDLE_SUITES,
  canonicalJson,
  computeBundleRowSha256,
  loadAndValidateBundle
} from './bundle/schema';
export type {
  BlindedCondition,
  BundleMessage,
  BundleResponseRow,
  BundleRowPayload,
  BundleSuite
} from './bundle/schema';
export {
  DEFAULT_SUITE_DIMENSIONS,
  DIMENSION_RUBRICS,
  JUDGE_DIMENSIONS,
  loadSuiteDimensionConfig
} from './bundle/dimensions';
export type { JudgeDimension, SuiteDimensionConfig } from './bundle/dimensions';
export { DimensionalLLMVerifier } from './verifiers/dimensional';
export type {
  DimensionalJudgment,
  DimensionalVerifierReceipt,
  DimensionScore
} from './verifiers/dimensional';
export type { 
  HarnessConfig, 
  ConstitutionConfig,
  ScenarioContext,
  ComplianceMetrics 
} from './types';
