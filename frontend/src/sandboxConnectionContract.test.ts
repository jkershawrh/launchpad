import { describe, expect, it } from 'vitest';
import { sandboxConnections } from './sandboxConnectionContract';

describe('sandboxConnections', () => {
  it('uses provisioned nested connection info and requested methods only', () => {
    expect(sandboxConnections({
      access_methods: ['jupyter', 'vscode'],
      connection_info: {
        jupyter_url: 'https://jupyter.example.test',
        vscode_url: 'https://code.example.test',
        ssh_password: 'generated-password',
      },
    })).toEqual({
      accessMethods: ['jupyter', 'vscode'],
      jupyterUrl: 'https://jupyter.example.test',
      vscodeUrl: 'https://code.example.test',
      accessPassword: 'generated-password',
    });
  });

  it('never invents localhost connection details', () => {
    expect(sandboxConnections({ access_methods: ['ssh'] })).toEqual({
      accessMethods: ['ssh'],
    });
  });

  it('exposes the real OpenShift console and web terminal entry points', () => {
    expect(sandboxConnections({
      access_methods: ['openshift_console', 'web_terminal'],
      connection_info: {
        openshift_console_url: 'https://console.example.test/topology/ns/lab-a',
        web_terminal_url: 'https://console.example.test/topology/ns/lab-a',
      },
    })).toEqual({
      accessMethods: ['openshift_console', 'web_terminal'],
      openshiftConsoleUrl: 'https://console.example.test/topology/ns/lab-a',
      webTerminalUrl: 'https://console.example.test/topology/ns/lab-a',
    });
  });
});
