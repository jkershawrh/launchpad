import { useState, useCallback } from 'react';
import {
  Button,
  Card,
  CardBody,
  CardTitle,
  EmptyState,
  EmptyStateBody,
  Gallery,
  GalleryItem,
  Label,
  PageSection,
  Pagination,
  Spinner,
  Alert,
  Content,
  MenuToggle,
  Select,
  SelectOption,
  Toolbar,
  ToolbarContent,
  ToolbarItem,
} from '@patternfly/react-core';
import { SyncIcon, CubesIcon } from '@patternfly/react-icons';
import { Table, Thead, Tr, Th, Tbody, Td } from '@patternfly/react-table';
import { useQueryClient } from '@tanstack/react-query';
import { useRequests, useRoutingDistribution, useLatencyPercentiles, useCostSummary } from '../api/hooks';
import HardwareBadge from '../components/HardwareBadge';

export default function Operations() {
  const [page, setPage] = useState(1);
  const [perPage, setPerPage] = useState(15);
  const [taskFilter, setTaskFilter] = useState('');
  const [taskOpen, setTaskOpen] = useState(false);

  const queryClient = useQueryClient();

  const params: Record<string, string> = { page: String(page), per_page: String(perPage) };
  if (taskFilter) params.task = taskFilter;

  const requests = useRequests(params);
  const distribution = useRoutingDistribution(7);
  const latency = useLatencyPercentiles(7);
  const cost = useCostSummary(30);

  const isRefreshing = requests.isFetching || distribution.isFetching || latency.isFetching || cost.isFetching;

  const handleRefresh = useCallback(() => {
    queryClient.invalidateQueries({ queryKey: ['requests'] });
    queryClient.invalidateQueries({ queryKey: ['routing-distribution'] });
    queryClient.invalidateQueries({ queryKey: ['latency-percentiles'] });
    queryClient.invalidateQueries({ queryKey: ['cost-summary'] });
  }, [queryClient]);

  const emptyMessage = 'No data yet — run workflows from the Try It page to generate analytics.';

  return (
    <>
      <PageSection>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
          <Content>
            <Content component={"h1"}>Platform Operations</Content>
            <Content component={"p"}>
              See which Intel hardware handled every request, how fast it ran, and what it cost.
              This data proves that intelligent routing across Xeon 6 and Gaudi cuts costs
              without sacrificing performance.
            </Content>
          </Content>
          <Button
            variant="secondary"
            icon={<SyncIcon />}
            onClick={handleRefresh}
            isLoading={isRefreshing}
            isDisabled={isRefreshing}
          >
            Refresh
          </Button>
        </div>
      </PageSection>

      <PageSection>
        <Gallery hasGutter minWidths={{ default: '280px' }}>
          {/* Routing Distribution Card */}
          <GalleryItem>
            <Card isFullHeight>
              <CardTitle>Routing Distribution (7d)</CardTitle>
              <CardBody>
                {distribution.isLoading ? (
                  <Spinner size="md" />
                ) : distribution.isError ? (
                  <Alert variant="warning" isInline isPlain title="Could not load routing distribution">
                    {String((distribution.error as Error)?.message || 'Unknown error')}
                  </Alert>
                ) : distribution.data?.data && distribution.data.data.length > 0 ? (
                  distribution.data.data.map((d) => (
                    <div key={d.backend} style={{ display: 'flex', justifyContent: 'space-between', padding: '0.25rem 0' }}>
                      <span>{d.backend}</span>
                      <span><strong>{d.pct}%</strong> ({d.count})</span>
                    </div>
                  ))
                ) : (
                  <EmptyState variant="xs" icon={CubesIcon} titleText="No data">
                    <EmptyStateBody>{emptyMessage}</EmptyStateBody>
                  </EmptyState>
                )}
              </CardBody>
            </Card>
          </GalleryItem>

          {/* Latency Percentiles Card */}
          <GalleryItem>
            <Card isFullHeight>
              <CardTitle>Latency Percentiles (7d)</CardTitle>
              <CardBody>
                {latency.isLoading ? (
                  <Spinner size="md" />
                ) : latency.isError ? (
                  <Alert variant="warning" isInline isPlain title="Could not load latency data">
                    {String((latency.error as Error)?.message || 'Unknown error')}
                  </Alert>
                ) : latency.data?.data && latency.data.data.length > 0 ? (
                  latency.data.data.map((l) => (
                    <div key={l.backend} style={{ padding: '0.25rem 0' }}>
                      <strong>{l.backend}</strong>
                      <div style={{ fontSize: '0.85rem', color: 'var(--pf-t--global--text--color--subtle)' }}>
                        p50: {l.p50_ms?.toFixed(0) ?? '—'}ms &bull; p95: {l.p95_ms?.toFixed(0) ?? '—'}ms &bull; p99: {l.p99_ms?.toFixed(0) ?? '—'}ms
                      </div>
                    </div>
                  ))
                ) : (
                  <EmptyState variant="xs" icon={CubesIcon} titleText="No data">
                    <EmptyStateBody>{emptyMessage}</EmptyStateBody>
                  </EmptyState>
                )}
              </CardBody>
            </Card>
          </GalleryItem>

          {/* Cost Summary Card */}
          <GalleryItem>
            <Card isFullHeight>
              <CardTitle>Cost Summary (30d)</CardTitle>
              <CardBody>
                {cost.isLoading ? (
                  <Spinner size="md" />
                ) : cost.isError ? (
                  <Alert variant="warning" isInline isPlain title="Could not load cost data">
                    {String((cost.error as Error)?.message || 'Unknown error')}
                  </Alert>
                ) : cost.data?.data && cost.data.data.length > 0 ? (
                  cost.data.data.map((c, i) => (
                    <div key={i} style={{ display: 'flex', justifyContent: 'space-between', padding: '0.25rem 0' }}>
                      <span>{c.backend} / {c.task}</span>
                      <span>${c.total_cost?.toFixed(4) ?? '0.0000'}</span>
                    </div>
                  ))
                ) : (
                  <EmptyState variant="xs" icon={CubesIcon} titleText="No data">
                    <EmptyStateBody>{emptyMessage}</EmptyStateBody>
                  </EmptyState>
                )}
              </CardBody>
            </Card>
          </GalleryItem>
        </Gallery>
      </PageSection>

      <PageSection variant="secondary">
        <Content>
          <Content component={"h2"}>Request History</Content>
        </Content>
        <Toolbar style={{ marginTop: '0.5rem' }}>
          <ToolbarContent>
            <ToolbarItem>
              <Select
                toggle={(ref) => (
                  <MenuToggle ref={ref} onClick={() => setTaskOpen(!taskOpen)} isExpanded={taskOpen}>
                    {taskFilter || 'All tasks'}
                  </MenuToggle>
                )}
                isOpen={taskOpen}
                onSelect={(_e, value) => { setTaskFilter(value as string); setTaskOpen(false); setPage(1); }}
                onOpenChange={setTaskOpen}
                selected={taskFilter}
              >
                <SelectOption value="">All tasks</SelectOption>
                <SelectOption value="embeddings">Embeddings</SelectOption>
                <SelectOption value="classification">Classification</SelectOption>
                <SelectOption value="completion">Completion</SelectOption>
              </Select>
            </ToolbarItem>
          </ToolbarContent>
        </Toolbar>
        {requests.isLoading ? <Spinner /> : requests.isError ? (
          <Alert variant="danger" title="Failed to load requests">
            {String((requests.error as Error)?.message || 'Check that the gateway is running and accessible.')}
          </Alert>
        ) : (
          <>
            <Table aria-label="Request history" variant="compact">
              <Thead>
                <Tr><Th>Time</Th><Th>Task</Th><Th>Backend</Th><Th>Hardware</Th><Th>Latency</Th><Th>Status</Th><Th>Reason</Th></Tr>
              </Thead>
              <Tbody>
                {requests.data?.data && requests.data.data.length > 0 ? requests.data.data.map((req) => (
                  <Tr key={req.id}>
                    <Td>{new Date(req.created_at).toLocaleString()}</Td>
                    <Td><Label isCompact>{req.task}</Label></Td>
                    <Td>{req.backend}</Td>
                    <Td><HardwareBadge accelerator={req.accelerator} /></Td>
                    <Td>{req.latency_ms?.toFixed(0) ?? '—'}ms</Td>
                    <Td><Label color={req.status === 'success' ? 'green' : 'red'} isCompact>{req.status}</Label></Td>
                    <Td style={{ maxWidth: '300px', overflow: 'hidden', textOverflow: 'ellipsis' }}>{req.reason}</Td>
                  </Tr>
                )) : (
                  <Tr><Td colSpan={7}>
                    <em>No requests recorded yet. Use the "Try It" page to send inference requests and generate data here.</em>
                  </Td></Tr>
                )}
              </Tbody>
            </Table>
            {requests.data?.data && requests.data.data.length > 0 && (
              <Pagination
                isCompact
                itemCount={(requests.data.data.length) < perPage ? perPage * (page - 1) + (requests.data.data.length) : undefined}
                perPage={perPage}
                page={page}
                onSetPage={(_e, p) => setPage(p)}
                onPerPageSelect={(_e, pp) => { setPerPage(pp); setPage(1); }}
              />
            )}
          </>
        )}
      </PageSection>
    </>
  );
}
