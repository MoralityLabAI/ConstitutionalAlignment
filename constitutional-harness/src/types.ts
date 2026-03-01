/**
 * Core type definitions for the Constitutional Alignment Harness
 */

export interface ConstitutionConfig {
  name: string;
  version: string;
  principles: Principle[];
  prohibitions: Prohibition[];
  obligations: Obligation[];
  eschatologicalFrame: EschatologicalFrame;
}

export interface Principle {
  id: string;
  name: string;
  description: string;
  quranicBasis?: string[]; // Ayat references
  priority: 'critical' | 'high' | 'medium' | 'low';
}

export interface Prohibition {
  id: string;
  category: string;
  description: string;
  examples: string[];
  severity: 'major' | 'minor';
}

export interface Obligation {
  id: string;
  category: string;
  description: string;
  examples: string[];
}

export interface EschatologicalFrame {
  enabled: boolean;
  framingText: string;
  accountabilityReminder: string;
}

export interface HarnessConfig {
  constitution: ConstitutionConfig;
  provider: 'anthropic' | 'openai' | 'custom';
  model: string;
  apiKey?: string;
  verification: VerificationConfig;
  logging: LoggingConfig;
}

export interface VerificationConfig {
  enabled: boolean;
  verifiers: string[]; // verifier IDs to use
  useVerifierLLM: boolean; // use LLM for ambiguous cases
  strictMode: boolean; // fail on any violation vs warn
}

export interface LoggingConfig {
  enabled: boolean;
  logPath?: string;
  logViolations: boolean;
  logMetrics: boolean;
}

export interface ScenarioContext {
  id: string;
  description: string;
  storyWorld?: string; // story world identifier
  turn: number;
  previousResponses?: string[];
  metadata?: Record<string, any>;
}

export interface ComplianceMetrics {
  totalResponses: number;
  violations: ViolationRecord[];
  complianceRate: number;
  violationsByCategory: Record<string, number>;
  violationsBySeverity: {
    critical: number;
    major: number;
    minor: number;
  };
}

export interface ViolationRecord {
  timestamp: Date;
  scenarioId: string;
  violationType: string;
  severity: 'critical' | 'major' | 'minor';
  description: string;
  response: string;
  verifierUsed: string;
}

export interface LLMRequest {
  prompt: string;
  context?: ScenarioContext;
  temperature?: number;
  maxTokens?: number;
  systemPrompt?: string;
}

export interface LLMResponse {
  content: string;
  model: string;
  usage?: {
    promptTokens: number;
    completionTokens: number;
    totalTokens: number;
  };
  raw?: any; // raw provider response
}
