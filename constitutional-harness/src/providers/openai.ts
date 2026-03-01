/**
 * OpenAI API Provider
 */

import { LLMProvider } from './base';
import { LLMRequest, LLMResponse } from '../types';

export class OpenAIProvider extends LLMProvider {
  private baseUrl = 'https://api.openai.com/v1/chat/completions';

  constructor(apiKey: string, model: string = 'gpt-4') {
    super(apiKey, model);
  }

  async generate(request: LLMRequest): Promise<LLMResponse> {
    const messages = [];
    
    if (request.systemPrompt) {
      messages.push({
        role: 'system',
        content: request.systemPrompt
      });
    }
    
    messages.push({
      role: 'user',
      content: request.prompt
    });

    const body = {
      model: this.model,
      messages,
      max_tokens: request.maxTokens || 4096,
      temperature: request.temperature ?? 0.7
    };

    const response = await this.makeRequest(this.baseUrl, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${this.apiKey}`
      },
      body: JSON.stringify(body)
    });

    const data = await response.json();
    
    return {
      content: data.choices[0].message.content,
      model: data.model,
      usage: {
        promptTokens: data.usage.prompt_tokens,
        completionTokens: data.usage.completion_tokens,
        totalTokens: data.usage.total_tokens
      },
      raw: data
    };
  }
}
