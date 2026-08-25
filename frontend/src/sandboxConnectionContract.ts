export interface SandboxConnections {
  accessMethods: string[];
  webConsoleUrl?: string;
  vscodeUrl?: string;
  jupyterUrl?: string;
  sshCommand?: string;
  sshInstructions?: string;
  accessPassword?: string;
}

export function sandboxConnections(resources: Record<string, unknown>): SandboxConnections {
  const info = (resources.connection_info || {}) as Record<string, unknown>;
  return {
    accessMethods: Array.isArray(resources.access_methods)
      ? resources.access_methods.map(String)
      : [],
    ...(typeof info.web_console_url === 'string' ? { webConsoleUrl: info.web_console_url } : {}),
    ...(typeof info.vscode_url === 'string' ? { vscodeUrl: info.vscode_url } : {}),
    ...(typeof info.jupyter_url === 'string' ? { jupyterUrl: info.jupyter_url } : {}),
    ...(typeof info.ssh === 'string' ? { sshCommand: info.ssh } : {}),
    ...(typeof info.ssh_instructions === 'string' ? { sshInstructions: info.ssh_instructions } : {}),
    ...(typeof info.ssh_password === 'string' ? { accessPassword: info.ssh_password } : {}),
  };
}
