export interface GuidedLabLinks {
  showroomUrl?: string;
  workspaceUrl?: string;
}

export function guidedLabLinks(resources: Record<string, unknown>): GuidedLabLinks {
  return {
    showroomUrl: typeof resources.showroom_url === 'string' ? resources.showroom_url : undefined,
    workspaceUrl: typeof resources.workspace_url === 'string' ? resources.workspace_url : undefined,
  };
}
