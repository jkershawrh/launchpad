import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import HardwareBadge from '../../components/HardwareBadge';

describe('HardwareBadge', () => {
  it('renders Xeon 6 for xeon6 accelerator', () => {
    render(<HardwareBadge accelerator="xeon6" />);
    expect(screen.getByText('Xeon 6')).toBeTruthy();
  });

  it('renders Gaudi for gaudi accelerator', () => {
    render(<HardwareBadge accelerator="gaudi" />);
    expect(screen.getByText('Gaudi')).toBeTruthy();
  });

  it('renders Local for local accelerator', () => {
    render(<HardwareBadge accelerator="local" />);
    expect(screen.getByText('Local')).toBeTruthy();
  });

  it('renders raw value for unknown accelerator', () => {
    render(<HardwareBadge accelerator="unknown-hw" />);
    expect(screen.getByText('unknown-hw')).toBeTruthy();
  });
});
