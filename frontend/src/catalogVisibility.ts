import type { CatalogItem } from './api/types';

export type ExposurePolicy = 'internal' | 'public_code';

const ALL_EXPOSURE_POLICIES: ExposurePolicy[] = ['internal', 'public_code'];

export function participantCatalog(items: CatalogItem[]): CatalogItem[] {
  return items.filter(
    (item) => item.status === 'active'
      && item.metadata?.migration_mode !== 'compatibility_alias'
      && item.metadata?.catalog_visibility !== 'internal_diagnostic'
      && item.metadata?.participant_orderable !== false,
  );
}

export function resolveParticipantCatalogId(
  items: CatalogItem[],
  requestedCatalogId: string,
): string {
  if (!requestedCatalogId) return '';

  const visibleIds = new Set(
    participantCatalog(items).map((item) => item.catalog_item_id),
  );
  if (visibleIds.has(requestedCatalogId)) return requestedCatalogId;

  const requestedItem = items.find(
    (item) => item.catalog_item_id === requestedCatalogId,
  );
  const canonicalId = requestedItem?.metadata?.canonical_item_id;
  return typeof canonicalId === 'string' && visibleIds.has(canonicalId)
    ? canonicalId
    : '';
}

export function allowedExposurePolicies(item?: CatalogItem): ExposurePolicy[] {
  if (!item) return ['internal'];

  const configured = item.metadata?.allowed_exposure_policies;
  if (!Array.isArray(configured)) return [...ALL_EXPOSURE_POLICIES];

  const allowed = configured.filter(
    (policy): policy is ExposurePolicy =>
      typeof policy === 'string'
      && ALL_EXPOSURE_POLICIES.includes(policy as ExposurePolicy),
  );
  return allowed.length > 0 ? allowed : ['internal'];
}

export function supportsExposurePolicy(
  item: CatalogItem | undefined,
  policy: ExposurePolicy,
): boolean {
  return allowedExposurePolicies(item).includes(policy);
}
