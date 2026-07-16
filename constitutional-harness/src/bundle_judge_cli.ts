import { AnthropicProvider } from './providers/anthropic';
import { LLMProvider } from './providers/base';
import { OpenAIProvider } from './providers/openai';
import { ingestResponseBundle } from './bundle/ingest';
import { BUNDLE_SUITES, BundleSuite } from './bundle/schema';

interface CliArgs {
  bundleDir: string;
  outputPath?: string;
  providerName?: 'anthropic' | 'openai';
  model?: string;
  suite?: BundleSuite;
  suiteConfigPath?: string;
  dryRun: boolean;
  help: boolean;
}

const USAGE = `Usage:
  npx tsx src/bundle_judge_cli.ts --bundle <directory> [options]

Options:
  --output <path>         Output JSONL (default: <bundle>/judge_scores.jsonl)
  --suite <suite>         Filter: storyworld, pressure, helpfulness, theology_guardrail
  --suite-config <path>   Override per-suite judge dimensions
  --provider <provider>   anthropic or openai (not needed for --dry-run)
  --model <model-id>      Judge model (or HARNESS_MODEL; not needed for --dry-run)
  --dry-run               Validate schema, all SHA-256 digests, and config without API calls
  --help                  Show this help

Environment:
  HARNESS_PROVIDER, HARNESS_MODEL, ANTHROPIC_API_KEY, OPENAI_API_KEY`;

function parseArgs(argv: string[]): CliArgs {
  const values = new Map<string, string>();
  let dryRun = false;
  let help = false;
  const valueFlags = new Set([
    '--bundle', '--output', '--provider', '--model', '--suite', '--suite-config'
  ]);
  for (let index = 0; index < argv.length; index += 1) {
    const arg = argv[index];
    if (arg === '--') {
      continue;
    }
    if (arg === '--dry-run') {
      dryRun = true;
      continue;
    }
    if (arg === '--help' || arg === '-h') {
      help = true;
      continue;
    }
    if (!valueFlags.has(arg)) {
      throw new Error(`Unknown argument: ${arg}\n\n${USAGE}`);
    }
    if (values.has(arg)) {
      throw new Error(`Argument may be provided only once: ${arg}`);
    }
    const value = argv[index + 1];
    if (!value || value.startsWith('--')) {
      throw new Error(`Missing value for argument: ${arg}`);
    }
    values.set(arg, value);
    index += 1;
  }

  const bundleDir = values.get('--bundle') || '';
  if (!help && bundleDir.length === 0) {
    throw new Error(`--bundle is required\n\n${USAGE}`);
  }
  const suiteValue = values.get('--suite');
  if (suiteValue && !BUNDLE_SUITES.some(suite => suite === suiteValue)) {
    throw new Error(`Unknown suite: ${suiteValue}`);
  }
  const providerValue = values.get('--provider');
  if (providerValue && providerValue !== 'anthropic' && providerValue !== 'openai') {
    throw new Error(`Unknown provider: ${providerValue}`);
  }

  return {
    bundleDir,
    outputPath: values.get('--output'),
    providerName: providerValue as CliArgs['providerName'],
    model: values.get('--model'),
    suite: suiteValue as BundleSuite | undefined,
    suiteConfigPath: values.get('--suite-config'),
    dryRun,
    help
  };
}

function resolveProviderName(
  explicit: CliArgs['providerName'],
  environment: NodeJS.ProcessEnv
): 'anthropic' | 'openai' {
  const configured = explicit || environment.HARNESS_PROVIDER?.trim();
  if (configured) {
    if (configured !== 'anthropic' && configured !== 'openai') {
      throw new Error('HARNESS_PROVIDER must be anthropic or openai');
    }
    return configured;
  }
  const hasAnthropic = Boolean(environment.ANTHROPIC_API_KEY?.trim());
  const hasOpenAI = Boolean(environment.OPENAI_API_KEY?.trim());
  if (hasAnthropic !== hasOpenAI) {
    return hasAnthropic ? 'anthropic' : 'openai';
  }
  throw new Error(
    'Set --provider (or HARNESS_PROVIDER); automatic selection requires exactly one provider API key'
  );
}

function initializeProvider(args: CliArgs, environment: NodeJS.ProcessEnv): LLMProvider {
  const providerName = resolveProviderName(args.providerName, environment);
  const model = args.model?.trim() || environment.HARNESS_MODEL?.trim();
  if (!model) {
    throw new Error('Set --model or HARNESS_MODEL for the judge model');
  }
  if (providerName === 'anthropic') {
    const apiKey = environment.ANTHROPIC_API_KEY?.trim();
    if (!apiKey) {
      throw new Error('ANTHROPIC_API_KEY is required for the Anthropic judge provider');
    }
    return new AnthropicProvider(apiKey, model);
  }
  const apiKey = environment.OPENAI_API_KEY?.trim();
  if (!apiKey) {
    throw new Error('OPENAI_API_KEY is required for the OpenAI judge provider');
  }
  return new OpenAIProvider(apiKey, model);
}

export async function main(
  argv: string[] = process.argv.slice(2),
  environment: NodeJS.ProcessEnv = process.env
): Promise<void> {
  const args = parseArgs(argv);
  if (args.help) {
    console.log(USAGE);
    return;
  }
  const summary = await ingestResponseBundle({
    bundleDir: args.bundleDir,
    outputPath: args.outputPath,
    suite: args.suite,
    suiteConfigPath: args.suiteConfigPath,
    dryRun: args.dryRun,
    providerFactory: args.dryRun ? undefined : () => initializeProvider(args, environment)
  });
  console.log(JSON.stringify(summary));
  if (summary.error_rows > 0) {
    process.exitCode = 2;
  }
}

if (require.main === module) {
  main().catch((error: unknown) => {
    const message = error instanceof Error ? error.message : String(error);
    console.error(message);
    process.exit(1);
  });
}
