export type HermesPolicy = {
  minSignalsForVerified: number;
  maxExternalCallsPerRun: number;
  cacheTtlMinutes: number;
  preferLocalFirst: boolean;
  semanticRecallEnabled: boolean;
};

const defaultPolicy: HermesPolicy = {
  minSignalsForVerified: 20,
  maxExternalCallsPerRun: 12,
  cacheTtlMinutes: 180,
  preferLocalFirst: true,
  semanticRecallEnabled: true,
};

let runtimePolicy: HermesPolicy = { ...defaultPolicy };

export function getPolicy(): HermesPolicy {
  return { ...runtimePolicy };
}

export function updatePolicy(input: Partial<HermesPolicy>): HermesPolicy {
  runtimePolicy = {
    minSignalsForVerified: Math.max(
      1,
      input.minSignalsForVerified ?? runtimePolicy.minSignalsForVerified,
    ),
    maxExternalCallsPerRun: Math.max(
      1,
      input.maxExternalCallsPerRun ?? runtimePolicy.maxExternalCallsPerRun,
    ),
    cacheTtlMinutes: Math.max(
      1,
      input.cacheTtlMinutes ?? runtimePolicy.cacheTtlMinutes,
    ),
    preferLocalFirst: input.preferLocalFirst ?? runtimePolicy.preferLocalFirst,
    semanticRecallEnabled:
      input.semanticRecallEnabled ?? runtimePolicy.semanticRecallEnabled,
  };
  return { ...runtimePolicy };
}

