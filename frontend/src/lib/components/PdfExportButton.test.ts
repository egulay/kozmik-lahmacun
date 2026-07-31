import { cleanup, render, screen } from '@testing-library/svelte';
import { afterEach, describe, expect, it } from 'vitest';
import { currentUser } from '$lib/session';
import PdfExportButton from './PdfExportButton.svelte';

describe('PdfExportButton', () => {
  afterEach(() => {
    currentUser.set(null);
    cleanup();
  });

  it('is only rendered for an administrator', () => {
    currentUser.set({
      userId: 'reporter',
      username: 'reporter@example.test',
      displayName: 'Demo Reporter',
      email: 'reporter@example.test',
      roles: ['REPORTER'],
      workspaceGeneration: 'test-generation'
    });
    const reporterView = render(PdfExportButton, {
      props: { documentId: 'execution-id', documentType: 'execution' }
    });
    expect(screen.queryByRole('button', { name: /pdf/i })).not.toBeInTheDocument();
    reporterView.unmount();

    currentUser.set({
      userId: 'admin',
      username: 'admin@example.test',
      displayName: 'Demo Admin',
      email: 'admin@example.test',
      roles: ['ADMIN'],
      workspaceGeneration: 'test-generation'
    });
    render(PdfExportButton, {
      props: { documentId: 'execution-id', documentType: 'execution' }
    });
    expect(screen.getByRole('button', { name: /pdf/i })).toBeVisible();
  });
});
