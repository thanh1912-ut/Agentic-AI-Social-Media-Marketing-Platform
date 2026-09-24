import type { RuntimeConfig } from '@/lib/api/config';

/** Serialize runtime config safely inside an inline HTML script element. */
export function serializeRuntimeConfigForInlineScript(config: RuntimeConfig): string {
  return JSON.stringify(config).replace(/</g, '\\u003c');
}
