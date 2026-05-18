import { useState, useEffect, useRef } from 'react';
import { Button, Card, CardBody, Content, Label, MenuToggle, PageSection, Select, SelectOption, Spinner } from '@patternfly/react-core';
import { api } from '../api/client';

const HW_COLORS: Record<string, string> = { xeon_eco: '#3e8635', xeon_performance: '#0068b5', gaudi_overdrive: '#e67e22' };
const HW_LABELS: Record<string, { label: string; color: 'green' | 'blue' | 'orange' }> = {
  xeon_eco: { label: 'Xeon 6 Eco', color: 'green' }, xeon_performance: { label: 'Xeon 6 + AMX', color: 'blue' }, gaudi_overdrive: { label: 'Gaudi', color: 'orange' },
};

interface AgentResult { agent_id: string; name: string; role: string; hardware_lane: string; hw_label: string; model: string; status: string; output: string; latency_ms: number; wave: number; }
interface WaveDef { wave: number; label: string; agents: string[]; depends_on: number | null; desc: string; }

const SCENARIOS = [
  { id: 'incident', name: 'Incident Investigation', desc: 'A P1 production incident: checkout degradation with Gaudi memory pressure. Agents triage, analyze logs, interpret metrics, find root cause, and report.' },
  { id: 'security_audit', name: 'Security Audit', desc: 'Comprehensive security audit: scan for CVEs, verify CIS compliance, analyze threat vectors, prioritize risks, and generate remediation plan.' },
  { id: 'capacity_planning', name: 'Capacity Planning', desc: 'Platform growth analysis: audit resource utilization, model traffic patterns, project growth, optimize costs, and plan procurement.' },
];

const DEPTHS = [
  { id: 'triage', label: 'Triage', agents: 3, waves: 2, time: '~3s', desc: 'Quick assessment' },
  { id: 'full', label: 'Full Investigation', agents: 5, waves: 3, time: '~8s', desc: 'Complete analysis' },
  { id: 'deep', label: 'Deep Analysis', agents: 8, waves: 4, time: '~15s', desc: 'Extended with validation & remediation' },
];

export default function SwarmDemo() {
  const [scenario, setScenario] = useState('incident');
  const [scenarioOpen, setScenarioOpen] = useState(false);
  const [depth, setDepth] = useState('full');
  const [loading, setLoading] = useState(false);
  const [agents, setAgents] = useState<AgentResult[]>([]);
  const [currentWave, setCurrentWave] = useState(0);
  const [done, setDone] = useState(false);
  const [finalReport, setFinalReport] = useState('');
  const [waveDefs, setWaveDefs] = useState<WaveDef[]>([]);
  const [swarmName, setSwarmName] = useState('');
  const [metrics, setMetrics] = useState<Record<string, unknown> | null>(null);
  const [expandedAgent, setExpandedAgent] = useState<string | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => () => { if (pollRef.current) clearInterval(pollRef.current); }, []);

  const runSwarm = async () => {
    setLoading(true); setAgents([]); setCurrentWave(0); setDone(false); setFinalReport('');
    setWaveDefs([]); setSwarmName(''); setMetrics(null); setExpandedAgent(null);
    try {
      const resp = await api.swarmRun(scenario, 42, depth) as { run_id: string };
      pollRef.current = setInterval(async () => {
        try {
          const s = await api.swarmStatus(resp.run_id) as Record<string, unknown>;
          setAgents((s.agent_results as AgentResult[]) || []);
          setCurrentWave(s.current_wave as number || 0);
          if (s.waves) setWaveDefs(s.waves as WaveDef[]);
          if (s.swarm_name) setSwarmName(s.swarm_name as string);
          if (s.status === 'completed') {
            setDone(true); setFinalReport(s.final_report as string || '');
            setMetrics({ hw_utilization: s.hw_utilization, parallel_speedup: s.parallel_speedup, total_ms: s.total_ms, agent_count: s.agent_count, wave_count: s.wave_count, route_counts: s.route_counts });
            setLoading(false);
            if (pollRef.current) clearInterval(pollRef.current);
          }
        } catch { /* retry */ }
      }, 800);
    } catch { setLoading(false); }
  };

  const agentMap = Object.fromEntries(agents.map(a => [a.agent_id, a]));
  const isIdle = agents.length === 0 && !loading;
  const scenarioMeta = SCENARIOS.find(s => s.id === scenario) || SCENARIOS[0];
  const depthMeta = DEPTHS.find(d => d.id === depth) || DEPTHS[1];

  return (
    <>
      <PageSection>
        <Content>
          <Content component="h1">Agent Swarm</Content>
          <Content component="p" style={{ maxWidth: '780px', fontSize: '1.05rem' }}>
            Multiple specialized AI agents coordinate across Intel Xeon 6 and Gaudi to solve
            complex problems. Fast tasks run on Xeon 6. Heavy reasoning runs on Gaudi.
            Agents work in waves — parallel where possible, sequential where dependencies exist.
          </Content>
        </Content>
      </PageSection>

      {/* Config + Launch */}
      {isIdle && (
        <PageSection variant="secondary">
          <div style={{ display: 'flex', gap: '16px', flexWrap: 'wrap', marginBottom: '16px', alignItems: 'flex-start' }}>
            {/* Scenario selector */}
            <div style={{ minWidth: '260px' }}>
              <div style={{ fontSize: '0.72rem', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.05em', color: 'var(--pf-t--global--text--color--subtle)', marginBottom: '4px' }}>Scenario</div>
              <Select
                isOpen={scenarioOpen}
                onOpenChange={setScenarioOpen}
                onSelect={(_e, val) => { setScenario(val as string); setScenarioOpen(false); }}
                selected={scenario}
                toggle={(toggleRef) => (
                  <MenuToggle ref={toggleRef} onClick={() => setScenarioOpen(!scenarioOpen)} isExpanded={scenarioOpen} style={{ width: '260px' }}>
                    {scenarioMeta.name}
                  </MenuToggle>
                )}
              >
                {SCENARIOS.map(s => <SelectOption key={s.id} value={s.id}>{s.name}</SelectOption>)}
              </Select>
            </div>

            {/* Depth selector */}
            <div>
              <div style={{ fontSize: '0.72rem', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.05em', color: 'var(--pf-t--global--text--color--subtle)', marginBottom: '4px' }}>Depth</div>
              <div style={{ display: 'flex', gap: '4px' }}>
                {DEPTHS.map(d => (
                  <button
                    key={d.id}
                    onClick={() => setDepth(d.id)}
                    style={{
                      padding: '6px 14px', borderRadius: '4px', border: `1px solid ${depth === d.id ? 'var(--pf-t--global--border--color--clicked)' : 'var(--pf-t--global--border--color--default)'}`,
                      background: depth === d.id ? 'var(--pf-t--global--background--color--primary--default)' : 'transparent',
                      color: depth === d.id ? '#fff' : 'var(--pf-t--global--text--color--regular)',
                      cursor: 'pointer', fontSize: '0.82rem', fontWeight: depth === d.id ? 700 : 400,
                    }}
                  >
                    {d.label} ({d.agents})
                  </button>
                ))}
              </div>
            </div>
          </div>

          {/* Scenario narrative */}
          <Card style={{ maxWidth: '700px', marginBottom: '16px' }}>
            <CardBody>
              <div style={{ fontWeight: 700, fontSize: '1rem', marginBottom: '4px' }}>{scenarioMeta.name}</div>
              <Content component="p" style={{ marginBottom: '8px', color: 'var(--rh-color--text-secondary)', fontSize: '0.88rem' }}>
                {scenarioMeta.desc}
              </Content>
              <div style={{ fontSize: '0.78rem', color: 'var(--rh-color--text-secondary)', marginBottom: '12px' }}>
                {depthMeta.agents} agents · {depthMeta.waves} waves · {depthMeta.time} · {depthMeta.desc}
              </div>
              <Button variant="primary" onClick={runSwarm}>Launch Swarm</Button>
            </CardBody>
          </Card>
        </PageSection>
      )}

      {/* Wave visualization */}
      {(loading || done) && (
        <PageSection>
          {/* Swarm header */}
          <div style={{ marginBottom: '16px' }}>
            <div style={{ fontWeight: 700, fontSize: '1rem' }}>{swarmName || scenarioMeta.name}</div>
            <div style={{ fontSize: '0.78rem', color: 'var(--rh-color--text-secondary)' }}>
              {depthMeta.label} · {depthMeta.agents} agents · {depthMeta.waves} waves
            </div>
          </div>

          {waveDefs.map((wave, wi) => {
            const waveAgents = wave.agents.map(id => agentMap[id]).filter(Boolean);
            const waveComplete = waveAgents.length === wave.agents.length && waveAgents.every(a => a.status === 'done');
            const waveActive = currentWave === wi + 1 && !waveComplete;
            const wavePending = currentWave < wi + 1;

            return (
              <div key={wi} style={{ marginBottom: '16px' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '8px' }}>
                  <div style={{
                    width: '28px', height: '28px', borderRadius: '50%', display: 'flex', alignItems: 'center', justifyContent: 'center',
                    fontSize: '0.75rem', fontWeight: 700, color: '#fff',
                    background: waveComplete ? '#3e8635' : waveActive ? '#0068b5' : '#555',
                    transition: 'background 0.3s',
                  }}>
                    {waveComplete ? '✓' : wi + 1}
                  </div>
                  <div>
                    <div style={{ fontWeight: 700, fontSize: '0.88rem', color: wavePending ? 'var(--rh-color--text-secondary)' : 'var(--rh-color--text)' }}>
                      Wave {wi + 1}: {wave.label}
                    </div>
                    <div style={{ fontSize: '0.72rem', color: 'var(--rh-color--text-secondary)' }}>{wave.desc}</div>
                  </div>
                  {waveActive && <Spinner size="md" />}
                </div>

                {/* Agent cards */}
                <div style={{ display: 'grid', gridTemplateColumns: `repeat(${Math.min(wave.agents.length, 3)}, 1fr)`, gap: '8px', marginLeft: '38px' }}>
                  {wave.agents.map(agentId => {
                    const a = agentMap[agentId];
                    const isDone = a?.status === 'done';
                    const hw = HW_LABELS[a?.hardware_lane || 'xeon_eco'] || HW_LABELS.xeon_eco;
                    const isExpanded = expandedAgent === agentId;

                    return (
                      <Card key={agentId} style={{
                        borderLeft: `3px solid ${HW_COLORS[a?.hardware_lane || 'xeon_eco'] || '#555'}`,
                        opacity: a ? 1 : 0.4, cursor: isDone ? 'pointer' : 'default', transition: 'opacity 0.3s',
                      }} onClick={() => isDone && setExpandedAgent(isExpanded ? null : agentId)}>
                        <CardBody style={{ padding: '10px' }}>
                          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '4px' }}>
                            <span style={{ fontWeight: 700, fontSize: '0.82rem' }}>{a?.name || agentId}</span>
                            <Label isCompact color={hw.color}>{hw.label}</Label>
                          </div>
                          <div style={{ fontSize: '0.72rem', color: 'var(--rh-color--text-secondary)', marginBottom: '4px' }}>{a?.role || '...'}</div>
                          {a?.status === 'running' && (
                            <div style={{ fontSize: '0.72rem' }}><Spinner size="sm" /> Running...</div>
                          )}
                          {isDone && (
                            <div style={{ fontSize: '0.72rem' }}>
                              <Label isCompact color="green">DONE</Label>
                              <span style={{ marginLeft: '6px', fontFamily: 'var(--pf-t--global--font--family--mono)' }}>{a.latency_ms.toFixed(0)}ms</span>
                            </div>
                          )}
                          {isExpanded && a?.output && (
                            <div style={{
                              marginTop: '8px', padding: '8px', borderRadius: '4px', fontSize: '0.78rem',
                              background: 'var(--rh-color--surface-secondary)', whiteSpace: 'pre-wrap', lineHeight: '1.5',
                              maxHeight: '200px', overflowY: 'auto',
                            }}>
                              {a.output}
                            </div>
                          )}
                        </CardBody>
                      </Card>
                    );
                  })}
                </div>
              </div>
            );
          })}

          {/* Summary metrics */}
          {done && metrics && (
            <Card style={{ marginTop: '16px', marginBottom: '16px', borderTop: '4px solid #0068b5' }}>
              <CardBody>
                <div style={{ fontWeight: 700, fontSize: '0.88rem', marginBottom: '12px' }}>Swarm Performance</div>
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '12px', marginBottom: '16px' }}>
                  {[
                    { v: (metrics.agent_count as number), l: 'Agents' },
                    { v: (metrics.wave_count as number), l: 'Waves' },
                    { v: `${((metrics.total_ms as number) / 1000).toFixed(1)}s`, l: 'Wall Time' },
                    { v: `${(metrics.parallel_speedup as number)}x`, l: 'Parallel Speedup' },
                  ].map(m => (
                    <div key={m.l} style={{ textAlign: 'center' }}>
                      <div style={{ fontSize: '1.4rem', fontWeight: 700, fontFamily: 'var(--pf-t--global--font--family--mono)' }}>{m.v}</div>
                      <div style={{ fontSize: '0.72rem', color: 'var(--rh-color--text-secondary)' }}>{m.l}</div>
                    </div>
                  ))}
                </div>

                {/* Hardware utilization bars */}
                <div style={{ fontSize: '0.72rem', fontWeight: 600, marginBottom: '6px' }}>Hardware Utilization</div>
                {Object.entries(metrics.hw_utilization as Record<string, number>).map(([lane, pct]) => {
                  const hw = HW_LABELS[lane] || { label: lane, color: 'grey' as const };
                  return (
                    <div key={lane} style={{ marginBottom: '6px' }}>
                      <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.72rem', marginBottom: '2px' }}>
                        <span>{hw.label}</span>
                        <span style={{ fontFamily: 'var(--pf-t--global--font--family--mono)', fontWeight: 700 }}>{pct}%</span>
                      </div>
                      <div style={{ height: '8px', borderRadius: '4px', background: 'var(--rh-color--surface-secondary)', overflow: 'hidden' }}>
                        <div style={{ height: '100%', width: `${pct}%`, background: HW_COLORS[lane] || '#888', borderRadius: '4px' }} />
                      </div>
                    </div>
                  );
                })}
              </CardBody>
            </Card>
          )}

          {/* Final report */}
          {done && finalReport && (
            <Card style={{ marginTop: '16px', borderTop: '4px solid #3e8635' }}>
              <CardBody>
                <div style={{ fontWeight: 700, fontSize: '1rem', marginBottom: '8px' }}>Swarm Output: Final Report</div>
                <div style={{ fontSize: '0.85rem', whiteSpace: 'pre-wrap', lineHeight: '1.6', padding: '12px', borderRadius: '6px', background: 'var(--rh-color--surface-secondary)' }}>
                  {finalReport}
                </div>
                <div style={{ marginTop: '12px', fontSize: '0.78rem', color: 'var(--rh-color--text-secondary)' }}>
                  {String(metrics?.agent_count)} agents · {String(metrics?.wave_count)} waves · Intel Xeon 6 + Gaudi · Simulated
                </div>
                <Button variant="secondary" style={{ marginTop: '8px' }} onClick={() => { setAgents([]); setDone(false); setFinalReport(''); setCurrentWave(0); setWaveDefs([]); setMetrics(null); }}>
                  Run Again
                </Button>
              </CardBody>
            </Card>
          )}
        </PageSection>
      )}
    </>
  );
}
