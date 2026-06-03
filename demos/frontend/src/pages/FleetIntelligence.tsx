import { useState } from 'react';
import { useFleetHealth, useFeedbackSummary } from '../api/hooks';
import type { ClusterCapacity, HealthAlert, FeedbackSummary } from '../api/types';
import '../styles/fleet-intel.css';

const HEALTH_COLORS: Record<string, string> = {
  healthy: '#3e8635',
  degraded: '#f0ab00',
  unhealthy: '#c9190b',
  unknown: '#6a6e73',
};

const SEVERITY_COLORS: Record<string, string> = {
  critical: '#c9190b',
  warning: '#f0ab00',
  info: '#0068b5',
};

const REC_COLORS: Record<string, string> = {
  preferred: '#3e8635',
  acceptable: '#f0ab00',
  avoid: '#c9190b',
};

function HealthDot({ status }: { status: string }) {
  return (
    <span
      className="fi-health-dot"
      style={{ backgroundColor: HEALTH_COLORS[status] || HEALTH_COLORS.unknown }}
    />
  );
}

function ScoreBar({ value, max = 100, color = '#0068b5' }: { value: number; max?: number; color?: string }) {
  const pct = Math.min(100, (value / max) * 100);
  return (
    <div className="fi-score-bar">
      <div className="fi-score-bar-fill" style={{ width: `${pct}%`, backgroundColor: color }} />
      <span className="fi-score-bar-label">{Math.round(value)}</span>
    </div>
  );
}

function ClusterCard({
  cluster,
  selected,
  onClick,
}: {
  cluster: ClusterCapacity;
  selected: boolean;
  onClick: () => void;
}) {
  const borderColor = HEALTH_COLORS[cluster.health_status] || HEALTH_COLORS.unknown;
  return (
    <div
      className={`fi-cluster-card ${selected ? 'fi-cluster-card--selected' : ''}`}
      style={{ borderColor }}
      onClick={onClick}
    >
      <div className="fi-cluster-header">
        <HealthDot status={cluster.health_status} />
        <span className="fi-cluster-name">{cluster.cluster_name}</span>
      </div>
      <div className="fi-cluster-body">
        <div className="fi-metric">
          <span className="fi-metric-label">Capacity</span>
          <ScoreBar value={cluster.score} color="#0068b5" />
        </div>
        {cluster.cpu_utilization != null && (
          <div className="fi-metric">
            <span className="fi-metric-label">CPU</span>
            <ScoreBar value={cluster.cpu_utilization * 100} color={cluster.cpu_utilization > 0.8 ? '#c9190b' : '#3e8635'} />
          </div>
        )}
        <div className="fi-metric">
          <span className="fi-metric-label">GPU</span>
          <span className={`fi-gpu-badge ${cluster.gpu_available ? 'fi-gpu-badge--on' : ''}`}>
            {cluster.gpu_available ? 'Available' : 'N/A'}
          </span>
        </div>
      </div>
    </div>
  );
}

function AlertBanner({ alerts }: { alerts: HealthAlert[] }) {
  if (alerts.length === 0) {
    return (
      <div className="fi-alert fi-alert--ok">
        <span className="fi-alert-dot" style={{ backgroundColor: '#3e8635' }} />
        All Systems Normal
      </div>
    );
  }

  const hasCritical = alerts.some((a) => a.severity === 'critical');
  const severity = hasCritical ? 'critical' : 'warning';

  return (
    <div className={`fi-alert fi-alert--${severity}`}>
      <span className="fi-alert-dot" style={{ backgroundColor: SEVERITY_COLORS[severity] }} />
      {alerts.length} alert{alerts.length !== 1 ? 's' : ''}
      <span className="fi-alert-details">
        {alerts.map((a) => (
          <span key={a.alert_id} className="fi-alert-item">
            {a.cluster_name}: {a.recommended_action}
          </span>
        ))}
      </span>
    </div>
  );
}

function FeedbackTable({ summaries }: { summaries: FeedbackSummary[] }) {
  if (summaries.length === 0) {
    return <div className="fi-empty">No feedback data yet</div>;
  }

  return (
    <table className="fi-table">
      <thead>
        <tr>
          <th>Cluster</th>
          <th>Catalog Item</th>
          <th>Hardware</th>
          <th>Attempts</th>
          <th>Success</th>
          <th>Latency</th>
          <th>Status</th>
        </tr>
      </thead>
      <tbody>
        {summaries.map((s) => {
          const pct = Math.round(s.success_rate * 100);
          return (
            <tr key={`${s.cluster_name}-${s.catalog_item_id}-${s.hardware_profile}`}>
              <td>{s.cluster_name}</td>
              <td className="fi-td-mono">{s.catalog_item_id}</td>
              <td>{s.hardware_profile}</td>
              <td>{s.total_attempts}</td>
              <td>
                <span className="fi-success-bar">
                  <span
                    className="fi-success-bar-fill"
                    style={{
                      width: `${pct}%`,
                      backgroundColor: pct >= 80 ? '#3e8635' : pct >= 30 ? '#f0ab00' : '#c9190b',
                    }}
                  />
                  <span className="fi-success-bar-label">{pct}%</span>
                </span>
              </td>
              <td className="fi-td-mono">{Math.round(s.avg_latency_ms)}ms</td>
              <td>
                <span
                  className="fi-rec-badge"
                  style={{ backgroundColor: REC_COLORS[s.recommendation] || '#6a6e73' }}
                >
                  {s.recommendation}
                </span>
              </td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}

export default function FleetIntelligence() {
  const { data: health, isLoading: healthLoading } = useFleetHealth();
  const { data: feedback } = useFeedbackSummary();
  const [selectedCluster, setSelectedCluster] = useState<string | null>(null);

  const clusters = health?.clusters || [];
  const alerts = health?.alerts || [];
  const summaries = feedback?.summaries || [];

  return (
    <div className="fi-page">
      <div className="fi-container">
        {/* Header */}
        <div className="fi-header">
          <div className="fi-title">
            <span className="fi-title-accent">FLEET</span> INTELLIGENCE
          </div>
          <span className={`fi-live-badge ${healthLoading ? '' : 'fi-live-badge--active'}`}>
            {healthLoading ? 'CONNECTING...' : 'LIVE'}
          </span>
        </div>

        {/* Alerts */}
        <AlertBanner alerts={alerts} />

        {/* Cluster Grid */}
        <div className="fi-section">
          <h2 className="fi-section-title">Cluster Capacity</h2>
          {clusters.length === 0 ? (
            <div className="fi-empty">No cluster data available</div>
          ) : (
            <div className="fi-cluster-grid">
              {clusters.map((c) => (
                <ClusterCard
                  key={c.cluster_name}
                  cluster={c}
                  selected={selectedCluster === c.cluster_name}
                  onClick={() => setSelectedCluster(
                    selectedCluster === c.cluster_name ? null : c.cluster_name,
                  )}
                />
              ))}
            </div>
          )}
        </div>

        {/* Feedback / Success Rates */}
        <div className="fi-section">
          <h2 className="fi-section-title">Provisioning History</h2>
          <FeedbackTable summaries={summaries} />
        </div>
      </div>
    </div>
  );
}
