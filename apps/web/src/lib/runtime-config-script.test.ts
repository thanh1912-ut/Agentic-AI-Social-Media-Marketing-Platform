import { describe, expect, it } from 'vitest';

import { serializeRuntimeConfigForInlineScript } from './runtime-config-script';

describe('serializeRuntimeConfigForInlineScript', () => {
  it('escapes script-closing characters and keeps the JSON value intact', () => {
    const config = {
      apiBaseUrl: '</script><script>alert(1)</script>',
      environmentLabel: 'Pilot',
    };

    const serialized = serializeRuntimeConfigForInlineScript(config);

    expect(serialized).not.toContain('</script>');
    expect(JSON.parse(serialized)).toEqual(config);
  });
});
