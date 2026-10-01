import { afterEach, expect, it, vi } from 'vitest';
import { cleanup, render, screen, waitFor } from '@testing-library/react';
import { useUrlTab } from './url-tabs';
const navigation = vi.hoisted(() => ({ search: 'tab=sources' }));
vi.mock('next/navigation', () => ({ useSearchParams: () => new URLSearchParams(navigation.search) }));
const tabs = ['sources', 'reports'] as const;
function Probe() {
  const [tab] = useUrlTab('tab', 'sources', tabs);
  return <p role="status">{tab}</p>;
}
afterEach(() => { cleanup(); window.history.replaceState({}, '', '/'); });
it('updates the visible tab when a Next.js link changes search parameters in the same route', async () => {
  window.history.replaceState({}, '', '/research?tab=sources');
  navigation.search = 'tab=sources';
  const view = render(<Probe />);
  expect(screen.getByRole('status')).toHaveTextContent('sources');
  window.history.replaceState({}, '', '/research?tab=reports');
  navigation.search = 'tab=reports';
  view.rerender(<Probe />);
  await waitFor(() => expect(screen.getByRole('status')).toHaveTextContent('reports'));
  window.history.replaceState({}, '', '/research?tab=invalid');
  navigation.search = 'tab=invalid';
  view.rerender(<Probe />);
  await waitFor(() => expect(screen.getByRole('status')).toHaveTextContent('sources'));
});
