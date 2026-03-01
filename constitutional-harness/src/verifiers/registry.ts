/**
 * Verifier registry and builder.
 */

import { HarnessConfig } from '../types';
import { LLMProvider } from '../providers/base';
import { HeuristicVerifier, Verifier } from './base';
import { LLMVerifier } from './llm';

export type VerifierFactory = (args: {
  config: HarnessConfig;
  provider: LLMProvider;
}) => Verifier;

export type VerifierFactoryMap = Record<string, VerifierFactory>;

const builtinFactories: VerifierFactoryMap = {
  heuristic: ({ config }) => new HeuristicVerifier(config.constitution),
  llm: ({ config, provider }) => new LLMVerifier(config.constitution, provider),
  'llm-verifier': ({ config, provider }) => new LLMVerifier(config.constitution, provider)
};

export function buildVerifierList(args: {
  config: HarnessConfig;
  provider: LLMProvider;
  verifierFactories?: VerifierFactoryMap;
}): Verifier[] {
  const { config, provider, verifierFactories } = args;
  const mergedFactories: VerifierFactoryMap = {
    ...builtinFactories,
    ...(verifierFactories || {})
  };

  const requested = config.verification.verifiers.length > 0
    ? config.verification.verifiers
    : ['heuristic'];

  const verifiers: Verifier[] = [];
  for (const rawName of requested) {
    const name = rawName.trim();
    if (!name) {
      continue;
    }
    if ((name === 'llm' || name === 'llm-verifier') && !config.verification.useVerifierLLM) {
      continue;
    }
    const factory = mergedFactories[name];
    if (!factory) {
      throw new Error(`Unknown verifier: ${name}`);
    }
    verifiers.push(factory({ config, provider }));
  }

  // Always provide at least one verifier when verification is enabled.
  if (verifiers.length === 0) {
    verifiers.push(new HeuristicVerifier(config.constitution));
  }

  return verifiers;
}
