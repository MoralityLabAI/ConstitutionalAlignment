export function requireHarnessModel(
  environment: NodeJS.ProcessEnv = process.env
): string {
  const model = environment.HARNESS_MODEL?.trim();
  if (!model) {
    throw new Error(
      'HARNESS_MODEL is required and must contain a provider model ID.'
    );
  }
  return model;
}
