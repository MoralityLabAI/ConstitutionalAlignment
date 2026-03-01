/**
 * Base LLM Provider Interface
 */

import { LLMRequest, LLMResponse } from '../types';

export abstract class LLMProvider {
  constructor(
    protected apiKey: string,
    protected model: string
  ) {}

  abstract generate(request: LLMRequest): Promise<LLMResponse>;

  protected async makeRequest(
    url: string,
    options: RequestInit
  ): Promise<Response> {
    const response = await fetch(url, options);
    
    if (!response.ok) {
      const error = await response.text();
      throw new Error(`API request failed: ${response.status} ${error}`);
    }
    
    return response;
  }
}
