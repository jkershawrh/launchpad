import {
  Card, CardBody, CardTitle, Content, Gallery, GalleryItem,
  Label, LabelGroup, PageSection, Spinner, Alert,
} from '@patternfly/react-core';
import { Table, Thead, Tr, Th, Tbody, Td } from '@patternfly/react-table';
import { useBackends, useRoutes } from '../api/hooks';
import HardwareBadge from '../components/HardwareBadge';
import RequestFlowDiagram from '../components/RequestFlowDiagram';
import WorkflowDiagrams from '../components/WorkflowDiagrams';

export default function Architecture() {
  const backends = useBackends();
  const routes = useRoutes();

  return (
    <>
      <PageSection>
        <Content>
          <Content component="h1">Platform Architecture</Content>
          <Content component="p" style={{ maxWidth: '720px' }}>
            One gateway. Two Intel hardware paths. Every request gets routed to the right
            place: Intel Xeon 6 for speed and cost efficiency, Intel Gaudi for throughput and
            large model generation. The gateway evaluates task type, model size, and priority —
            then returns the result with full routing reasoning.
          </Content>
        </Content>
      </PageSection>

      <PageSection variant="secondary">
        <Content><Content component="h2">Request Flow</Content></Content>
        <RequestFlowDiagram />
      </PageSection>

      <PageSection>
        <Content>
          <Content component="h2">Multi-Step Workflow Routing</Content>
          <Content component="p" style={{ maxWidth: '720px', marginBottom: '1rem' }}>
            Real AI pipelines aren't single-step. Embeddings are fast and small — run them on
            Xeon 6. Generation is slow and large — route it to Gaudi. This platform makes that
            decision for each step independently, all through one API call.
          </Content>
        </Content>
        <WorkflowDiagrams />
      </PageSection>

      <PageSection variant="secondary">
        <Content><Content component="h2">Inference Backends</Content></Content>
        {backends.isLoading ? <Spinner aria-label="Loading" /> : backends.isError ? (
          <Alert variant="warning" title="Backends unavailable — gateway may still be starting">
            <p>Refresh the page once the gateway is ready.</p>
          </Alert>
        ) : (
          <Gallery hasGutter minWidths={{ default: '300px' }} style={{ marginTop: '1rem' }}>
            {backends.data?.backends.map((b) => (
              <GalleryItem key={b.name}>
                <Card isFullHeight>
                  <CardTitle><HardwareBadge accelerator={b.accelerator} /> {b.name}</CardTitle>
                  <CardBody>
                    <LabelGroup>{b.capabilities.map((c) => <Label key={c} isCompact>{c}</Label>)}</LabelGroup>
                    <Content component="small" style={{ marginTop: '0.5rem', display: 'block' }}>
                      ${b.cost_per_1k_tokens}/1K tokens | {b.healthy ? 'Online' : 'Offline'}
                    </Content>
                  </CardBody>
                </Card>
              </GalleryItem>
            ))}
          </Gallery>
        )}
      </PageSection>

      <PageSection>
        <Content><Content component="h2">Routing Rules</Content></Content>
        {routes.isLoading ? <Spinner aria-label="Loading" /> : routes.isError ? (
          <Alert variant="warning" title="Routes unavailable — gateway may still be starting" />
        ) : (
          <Table aria-label="Routing rules" variant="compact" style={{ marginTop: '1rem' }}>
            <Thead><Tr><Th>Task</Th><Th>Backend</Th><Th>Why</Th></Tr></Thead>
            <Tbody>
              {(routes.data?.routes || []).map((r, i) => (
                <Tr key={r.task + '-' + i}>
                  <Td><Label isCompact>{r.task}</Label></Td>
                  <Td>{r.backend || r.default_backend || 'conditional'}</Td>
                  <Td><em>{r.reason || ''}</em></Td>
                </Tr>
              ))}
            </Tbody>
          </Table>
        )}
      </PageSection>

      <PageSection variant="secondary">
        <Content>
          <Content component="h3">The Key Insight</Content>
          <Content component="p" style={{ maxWidth: '720px', fontStyle: 'italic' }}>
            "The routing decision is the demo. Every response includes which hardware was selected,
            why it was selected, the latency, and the cost estimate. That metadata is what makes
            Intel + Red Hat credible for enterprise AI."
          </Content>
        </Content>
      </PageSection>
    </>
  );
}
