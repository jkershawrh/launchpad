import { describe, expect, it } from 'vitest';
import { sandboxConnections } from './sandboxConnectionContract';

describe('sandboxConnections', () => {
  it('uses provisioned nested connection info and requested methods only', () => {
    expect(sandboxConnections({
      access_methods: ['jupyter', 'vscode'],
      connection_info: {
        jupyter_url: 'https://jupyter.example.test',
        vscode_url: 'https://code.example.test',
      },
    })).toEqual({
      accessMethods: ['jupyter', 'vscode'],
      jupyterUrl: 'https://jupyter.example.test',
      vscodeUrl: 'https://code.example.test',
    });
  });

  it('never invents localhost connection details', () => {
    expect(sandboxConnections({ access_methods: ['ssh'] })).toEqual({
      accessMethods: ['ssh'],
    });
  });
});
