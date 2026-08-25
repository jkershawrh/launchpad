import { describe, expect, it } from 'vitest';
import { guidedLabLinks } from './guidedLabContract';

describe('guided lab access contract', () => {
  it('exposes the visual guide and live workspace separately', () => {
    expect(guidedLabLinks({
      showroom_url: 'https://showroom.example.test',
      workspace_url: 'https://workspace.example.test',
    })).toEqual({
      showroomUrl: 'https://showroom.example.test',
      workspaceUrl: 'https://workspace.example.test',
    });
  });

  it('does not invent fallback URLs', () => {
    expect(guidedLabLinks({})).toEqual({
      showroomUrl: undefined,
      workspaceUrl: undefined,
    });
  });
});
