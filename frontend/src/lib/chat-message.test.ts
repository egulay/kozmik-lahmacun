import { describe, expect, it } from 'vitest';
import { linkExecutionReferences } from './chat-message';

describe('linkExecutionReferences', () => {
  it('links an English execution reference without changing surrounding text', () => {
    const id = '21b05626-51c0-4868-ad27-bebba5e3de5d';
    const parts = linkExecutionReferences(`Request received. Execution ID: ${id}.`);

    expect(parts.find((part) => part.executionId)?.executionId).toBe(id);
    expect(parts.map((part) => part.text).join('')).toBe(
      `Request received. Execution ID: ${id}.`
    );
  });

  it('links a Turkish execution reference', () => {
    const id = '21b05626-51c0-4868-ad27-bebba5e3de5d';

    expect(
      linkExecutionReferences(`Çalıştırma kimliği: ${id}`)[1].executionId
    ).toBe(id);
  });
});
