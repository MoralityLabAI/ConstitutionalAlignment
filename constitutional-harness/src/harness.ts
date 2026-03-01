/**
 * Constitutional Alignment Harness
 * Main orchestrator for constitutional AI alignment
 */

import { 
  HarnessConfig, 
  LLMRequest, 
  LLMResponse, 
  ScenarioContext,
  ComplianceMetrics,
  ViolationRecord
} from './types';
import { LLMProvider } from './providers/base';
import { AnthropicProvider } from './providers/anthropic';
import { OpenAIProvider } from './providers/openai';
import { Verifier, VerificationResult } from './verifiers/base';
import { buildVerifierList, type VerifierFactoryMap } from './verifiers/registry';
import * as fs from 'fs';
import * as path from 'path';

export class ConstitutionalHarness {
  private provider: LLMProvider;
  private verifiers: Verifier[] = [];
  private metrics: ComplianceMetrics;
  private logStream?: fs.WriteStream;

  constructor(
    private config: HarnessConfig,
    private options?: {
      verifierFactories?: VerifierFactoryMap;
    }
  ) {
    this.provider = this.initializeProvider();
    this.initializeVerifiers();
    this.metrics = this.initializeMetrics();
    this.initializeLogging();
  }

  private initializeProvider(): LLMProvider {
    const apiKey = this.config.apiKey || process.env.ANTHROPIC_API_KEY || process.env.OPENAI_API_KEY || '';
    
    switch (this.config.provider) {
      case 'anthropic':
        return new AnthropicProvider(apiKey, this.config.model);
      case 'openai':
        return new OpenAIProvider(apiKey, this.config.model);
      default:
        throw new Error(`Unsupported provider: ${this.config.provider}`);
    }
  }

  private initializeVerifiers(): void {
    this.verifiers = buildVerifierList({
      config: this.config,
      provider: this.provider,
      verifierFactories: this.options?.verifierFactories
    });
  }

  private initializeMetrics(): ComplianceMetrics {
    return {
      totalResponses: 0,
      violations: [],
      complianceRate: 1.0,
      violationsByCategory: {},
      violationsBySeverity: {
        critical: 0,
        major: 0,
        minor: 0
      }
    };
  }

  private initializeLogging(): void {
    if (!this.config.logging.enabled || !this.config.logging.logPath) {
      return;
    }

    const logDir = path.dirname(this.config.logging.logPath);
    if (!fs.existsSync(logDir)) {
      fs.mkdirSync(logDir, { recursive: true });
    }

    this.logStream = fs.createWriteStream(this.config.logging.logPath, { flags: 'a' });
  }

  /**
   * Generate a response with constitutional alignment
   */
  async generate(
    prompt: string,
    context?: ScenarioContext,
    options?: Partial<LLMRequest>
  ): Promise<LLMResponse> {
    // Build system prompt with constitutional framing
    const systemPrompt = this.buildSystemPrompt();

    // Add eschatological reminder to user prompt
    const framedPrompt = this.framePrompt(prompt);

    // Generate response
    const request: LLMRequest = {
      prompt: framedPrompt,
      context,
      systemPrompt,
      temperature: options?.temperature,
      maxTokens: options?.maxTokens
    };

    const response = await this.provider.generate(request);

    // Verify response
    if (this.config.verification.enabled) {
      await this.verifyResponse(response, context);
    }

    // Update metrics
    this.updateMetrics(response);

    // Log if enabled
    if (this.config.logging.enabled) {
      this.log('response', { prompt, response, context });
    }

    return response;
  }

  /**
   * Verify a response against constitutional principles
   */
  async verifyResponse(
    response: LLMResponse,
    context?: ScenarioContext
  ): Promise<VerificationResult[]> {
    const results: VerificationResult[] = [];

    for (const verifier of this.verifiers) {
      const result = await verifier.verify(response, context);
      results.push(result);

      // Record violations
      if (!result.passed) {
        this.recordViolations(result, response, context);
      }

      // In strict mode, throw on first violation
      if (this.config.verification.strictMode && !result.passed) {
        throw new Error(
          `Constitutional violation detected by ${result.verifier}: ${
            result.violations[0]?.description || 'Unknown violation'
          }`
        );
      }
    }

    return results;
  }

  /**
   * Convenience wrapper for verifying arbitrary text (e.g., TRM rationales, story-world artifacts).
   */
  async verifyText(
    content: string,
    context?: ScenarioContext,
    model = 'external'
  ): Promise<VerificationResult[]> {
    return this.verifyResponse({ content, model }, context);
  }

  /**
   * Convenience wrapper for verifying a JSON-serializable artifact.
   */
  async verifyStoryWorld(
    storyWorld: unknown,
    context?: ScenarioContext,
    model = 'external'
  ): Promise<VerificationResult[]> {
    const serialized =
      typeof storyWorld === 'string' ? storyWorld : JSON.stringify(storyWorld, null, 2);
    return this.verifyResponse({ content: serialized, model }, context);
  }

  /**
   * Add a verifier instance at runtime (useful for ad-hoc integration and experiments).
   */
  registerVerifier(verifier: Verifier): void {
    this.verifiers.push(verifier);
  }

  private buildSystemPrompt(): string {
    const constitution = this.config.constitution;
    
    let systemPrompt = '';

    // Add eschatological framing
    if (constitution.eschatologicalFrame.enabled) {
      systemPrompt += constitution.eschatologicalFrame.framingText + '\n\n';
    }

    // Add principles
    systemPrompt += 'CONSTITUTIONAL PRINCIPLES TO UPHOLD:\n';
    for (const principle of constitution.principles) {
      systemPrompt += `- ${principle.name}: ${principle.description}\n`;
      if (principle.quranicBasis && principle.quranicBasis.length > 0) {
        systemPrompt += `  (Quranic basis: ${principle.quranicBasis.join(', ')})\n`;
      }
    }

    systemPrompt += '\nPROHIBITIONS TO AVOID:\n';
    for (const prohibition of constitution.prohibitions) {
      systemPrompt += `- ${prohibition.category}: ${prohibition.description}\n`;
    }

    systemPrompt += '\nOBLIGATIONS TO FULFILL:\n';
    for (const obligation of constitution.obligations) {
      systemPrompt += `- ${obligation.category}: ${obligation.description}\n`;
    }

    return systemPrompt;
  }

  private framePrompt(prompt: string): string {
    if (!this.config.constitution.eschatologicalFrame.enabled) {
      return prompt;
    }

    const reminder = this.config.constitution.eschatologicalFrame.accountabilityReminder;
    return `${reminder}\n\n${prompt}`;
  }

  private recordViolations(
    result: VerificationResult,
    response: LLMResponse,
    context?: ScenarioContext
  ): void {
    for (const violation of result.violations) {
      const record: ViolationRecord = {
        timestamp: new Date(),
        scenarioId: context?.id || 'unknown',
        violationType: violation.type,
        severity: violation.severity,
        description: violation.description,
        response: response.content,
        verifierUsed: result.verifier
      };

      this.metrics.violations.push(record);
      this.metrics.violationsBySeverity[violation.severity]++;
      
      const category = violation.type;
      this.metrics.violationsByCategory[category] = 
        (this.metrics.violationsByCategory[category] || 0) + 1;

      if (this.config.logging.logViolations) {
        this.log('violation', record);
      }
    }
  }

  private updateMetrics(response: LLMResponse): void {
    this.metrics.totalResponses++;
    this.metrics.complianceRate = 
      1 - (this.metrics.violations.length / this.metrics.totalResponses);
  }

  private log(type: string, data: any): void {
    if (!this.logStream) return;

    const logEntry = {
      timestamp: new Date().toISOString(),
      type,
      data
    };

    this.logStream.write(JSON.stringify(logEntry) + '\n');
  }

  /**
   * Get current compliance metrics
   */
  getMetrics(): ComplianceMetrics {
    return { ...this.metrics };
  }

  /**
   * Export metrics to file
   */
  exportMetrics(filepath: string): void {
    fs.writeFileSync(filepath, JSON.stringify(this.metrics, null, 2));
  }

  /**
   * Reset metrics
   */
  resetMetrics(): void {
    this.metrics = this.initializeMetrics();
  }

  /**
   * Close the harness and clean up resources
   */
  close(): void {
    if (this.logStream) {
      this.logStream.end();
    }
  }
}
