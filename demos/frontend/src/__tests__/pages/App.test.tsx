import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import AppLayout from '../../components/AppLayout';

function renderWithProviders(ui: React.ReactElement) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>{ui}</MemoryRouter>
    </QueryClientProvider>
  );
}

describe('AppLayout', () => {
  it('renders navigation with all page links', () => {
    renderWithProviders(<AppLayout />);
    expect(screen.getByText('Overview')).toBeTruthy();
    expect(screen.getByText('Architecture')).toBeTruthy();
    expect(screen.getByText('Try It')).toBeTruthy();
    expect(screen.getByText('Use Cases')).toBeTruthy();
    expect(screen.getByText('Operations')).toBeTruthy();
    expect(screen.getByText('Governance')).toBeTruthy();
    expect(screen.getByText('Documentation')).toBeTruthy();
  });

  it('shows platform title', () => {
    renderWithProviders(<AppLayout />);
    expect(screen.getByText(/Intel-Red Hat AI Inference Platform/i)).toBeTruthy();
  });
});
