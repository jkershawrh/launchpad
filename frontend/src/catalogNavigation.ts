export function catalogLaunchPath(category: string, catalogItemId: string): string {
  if (category === 'open_sandbox') return '/sandbox';
  if (category === 'guided_build') {
    return `/request?catalog_item=${encodeURIComponent(catalogItemId)}`;
  }
  return `/demos?launch=${encodeURIComponent(catalogItemId)}`;
}
