/**
 * Anthropic API Provider
 */

import { LLMProvider } from './base';
import { LLMRequest, LLMResponse } from '../types';

export class AnthropicProvider extends LLMProvider {
  private baseUrl = 'https://api.anthropic.com/v1/messages';
  private version = '2023-06-01';

  constructor(apiKey: string, model: string = 'claude-sonnet-4-20250514') {
    super(apiKey, model);
  }

  async generate(request: LLMRequest): Promise<LLMResponse> {
    const messages = [
      {
        role: 'user',
        content: request.prompt
      }
    ];

    const body = {
      model: this.model,
      max_tokens: request.maxTokens || 4096,
      temperature: request.temperature ?? 0.7,
      messages,
      ...(request.systemPrompt && { system: request.systemPrompt })
    };

    const response = await this.makeRequest(this.baseUrl, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'x-api-key': this.apiKey,
        'anthropic-version': this.version
      },
      body: JSON.stringify(body)
    });

    const data = await response.json();
    
    return {
      content: data.content[0].text,
      model: data.model,
      usage: {
        promptTokens: data.usage.input_tokens,
        completionTokens: data.usage.output_tokens,
        totalTokens: data.usage.input_tokens + data.usage.output_tokens
      },
      raw: data
    };
  }
}
