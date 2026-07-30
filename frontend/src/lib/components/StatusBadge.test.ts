import { cleanup, render, screen } from '@testing-library/svelte';
import { locale } from '$lib/i18n';
import { afterEach, describe, expect, it } from 'vitest';
import StatusBadge from './StatusBadge.svelte';

describe('StatusBadge', () => {
  afterEach(cleanup);

  it('renders a localized Turkish terminal success state', () => {
    locale.set('tr');
    render(StatusBadge, { props: { status: 'COMPLETED' } });
    expect(screen.getByText('Tamamlandı')).toBeVisible();
  });

  it('renders a localized English terminal success state', () => {
    locale.set('en');
    render(StatusBadge, { props: { status: 'COMPLETED' } });
    expect(screen.getByText('Completed')).toBeVisible();
  });
});
