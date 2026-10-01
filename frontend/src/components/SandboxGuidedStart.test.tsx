// @vitest-environment jsdom
import '@testing-library/jest-dom/vitest';
import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import SandboxGuidedStart from './SandboxGuidedStart';

describe('SandboxGuidedStart', () => {
  it('frames an optional story and a complete Show Learn Do Prove path', () => {
    render(<SandboxGuidedStart />);

    expect(screen.getByRole('heading', { name: 'Your first governed AI workload' })).toBeInTheDocument();
    expect(screen.getByText(/open sandbox stays open/i)).toBeInTheDocument();
    expect(screen.getByText(/assigned managed granite-2b-cpu model/i)).toBeInTheDocument();
    expect(screen.getByText(/model serving remains outside this sandbox/i)).toBeInTheDocument();
    for (const stage of ['Show', 'Learn', 'Do', 'Prove', 'Clean up']) {
      expect(screen.getByText(stage)).toBeInTheDocument();
    }
    expect(screen.getByText('launchpad-guided-start show')).toBeInTheDocument();
    expect(screen.getByText('launchpad-guided-start learn')).toBeInTheDocument();
    expect(screen.getByText('launchpad-guided-start do')).toBeInTheDocument();
    expect(screen.getByText('launchpad-guided-start prove')).toBeInTheDocument();
    expect(screen.getByText('launchpad-guided-start cleanup')).toBeInTheDocument();
    expect(screen.getByText(/guided-start-proof.json/i)).toBeInTheDocument();
  });
});
