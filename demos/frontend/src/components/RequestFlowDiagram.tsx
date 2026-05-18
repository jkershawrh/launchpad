import { Label } from '@patternfly/react-core';

const nodeStyle = (bg: string, border: string): React.CSSProperties => ({
  background: bg,
  border: `2px solid ${border}`,
  borderRadius: '12px',
  padding: '14px 24px',
  textAlign: 'center',
  fontWeight: 500,
  fontSize: '0.9rem',
  position: 'relative',
});

const connectorStyle: React.CSSProperties = {
  width: '2px',
  height: '28px',
  background: 'var(--pf-t--global--border--color--default)',
  margin: '0 auto',
};

const arrowDown: React.CSSProperties = {
  width: 0,
  height: 0,
  borderLeft: '6px solid transparent',
  borderRight: '6px solid transparent',
  borderTop: '8px solid var(--pf-t--global--border--color--default)',
  margin: '0 auto',
};

const splitConnector: React.CSSProperties = {
  display: 'flex',
  justifyContent: 'center',
  alignItems: 'flex-start',
  position: 'relative',
  marginTop: '4px',
};

const branchLine: React.CSSProperties = {
  position: 'absolute',
  top: 0,
  height: '2px',
  background: 'var(--pf-t--global--border--color--default)',
};

export default function RequestFlowDiagram() {
  return (
    <div role="img" aria-label="Request flow diagram: Partner App sends request to Inference Gateway, which routes to either Xeon 6 pool (embeddings, classification, reranking, small LLM) or Gaudi pool (large LLM, batch generation), then logs to PostgreSQL and Prometheus" style={{ maxWidth: '640px', margin: '0 auto', padding: '1.5rem 0' }}>
      {/* Source */}
      <div style={nodeStyle('var(--rh-color--surface)', 'var(--pf-t--global--border--color--default)')}>
        Partner Application / API Client
      </div>

      <div style={connectorStyle} />
      <div style={arrowDown} />

      {/* Gateway */}
      <div style={{
        ...nodeStyle('var(--pf-t--global--background--color--primary--default)', 'var(--pf-t--global--color--brand--default)'),
        boxShadow: '0 2px 8px rgba(0,0,0,0.08)',
      }}>
        <div style={{ fontSize: '1rem', fontWeight: 700, marginBottom: '4px' }}>
          Inference Gateway
        </div>
        <div style={{ fontSize: '0.8rem', opacity: 0.7 }}>
          Routing Policy &middot; Task Type &middot; Model Size &middot; Cost
        </div>
      </div>

      <div style={connectorStyle} />

      {/* Split label */}
      <div style={{ textAlign: 'center', fontSize: '0.8rem', color: 'var(--pf-t--global--text--color--subtle)', margin: '2px 0 8px' }}>
        routes to optimal hardware
      </div>

      {/* Branches */}
      <div style={splitConnector}>
        <div style={{ ...branchLine, left: '25%', right: '25%' }} />
      </div>

      <div style={{ display: 'flex', gap: '16px', marginTop: '6px' }}>
        {/* Xeon 6 */}
        <div style={{ flex: 1 }}>
          <div style={connectorStyle} />
          <div style={arrowDown} />
          <div style={{
            ...nodeStyle('var(--rh-color--xeon6-bg)', 'var(--rh-color--xeon6)'),
            borderRadius: '12px',
          }}>
            <Label color="blue" style={{ marginBottom: '8px' }}>Xeon 6</Label>
            <div style={{ fontSize: '0.82rem', lineHeight: '1.7', fontWeight: 400 }}>
              <div>Embeddings</div>
              <div>Classification</div>
              <div>Reranking</div>
              <div>Small LLM (&le; 8B)</div>
            </div>
            <div style={{ marginTop: '8px', fontSize: '0.75rem', opacity: 0.6 }}>
              $0.001–0.002 / 1K tokens
            </div>
          </div>
        </div>

        {/* Gaudi */}
        <div style={{ flex: 1 }}>
          <div style={connectorStyle} />
          <div style={arrowDown} />
          <div style={{
            ...nodeStyle('var(--rh-color--gaudi-bg)', 'var(--rh-color--gaudi)'),
            borderRadius: '12px',
          }}>
            <Label color="orange" style={{ marginBottom: '8px' }}>Gaudi</Label>
            <div style={{ fontSize: '0.82rem', lineHeight: '1.7', fontWeight: 400 }}>
              <div>Large LLM (&gt; 8B)</div>
              <div>Batch Generation</div>
            </div>
            <div style={{ marginTop: '8px', fontSize: '0.75rem', opacity: 0.6 }}>
              $0.008 / 1K tokens
            </div>
          </div>
        </div>
      </div>

      {/* Converge */}
      <div style={{ display: 'flex', gap: '16px' }}>
        <div style={{ flex: 1 }}><div style={connectorStyle} /></div>
        <div style={{ flex: 1 }}><div style={connectorStyle} /></div>
      </div>

      <div style={splitConnector}>
        <div style={{ ...branchLine, left: '25%', right: '25%' }} />
      </div>

      <div style={connectorStyle} />
      <div style={arrowDown} />

      {/* Observability */}
      <div style={{ display: 'flex', gap: '16px' }}>
        <div style={{
          ...nodeStyle('var(--rh-color--surface-secondary)', 'var(--pf-t--global--border--color--default)'),
          flex: 1,
          fontSize: '0.82rem',
        }}>
          <div style={{ fontWeight: 600, marginBottom: '2px' }}>PostgreSQL</div>
          <div style={{ opacity: 0.7 }}>Request history &middot; Audit trail</div>
        </div>
        <div style={{
          ...nodeStyle('var(--rh-color--surface-secondary)', 'var(--pf-t--global--border--color--default)'),
          flex: 1,
          fontSize: '0.82rem',
        }}>
          <div style={{ fontWeight: 600, marginBottom: '2px' }}>Prometheus</div>
          <div style={{ opacity: 0.7 }}>Metrics &middot; Grafana dashboard</div>
        </div>
      </div>
    </div>
  );
}
