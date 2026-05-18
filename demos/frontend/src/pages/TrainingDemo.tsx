import { useState, useEffect, useRef } from 'react';
import {
  Button, Card, CardBody, Content, Label, MenuToggle, PageSection, Select, SelectOption,
} from '@patternfly/react-core';
import { api } from '../api/client';

const TASKS = [
  { value: 'incident_rca_finetune', label: 'Incident RCA', desc: 'Better root cause analysis from alerts and logs' },
  { value: 'openshift_troubleshooting_finetune', label: 'OpenShift Troubleshooting', desc: 'OpenShift-specific error explanations' },
  { value: 'dashboard_vision_finetune', label: 'Dashboard Vision', desc: 'Dashboard screenshot interpretation' },
  { value: 'code_failure_finetune', label: 'Code Failure', desc: 'Build/test failure explanations' },
  { value: 'small_classifier_tune', label: 'Small Classifier', desc: 'Lightweight classifier for Xeon 6' },
];

const MODELS: Record<string, Array<{ value: string; label: string; params: string; hw: string }>> = {
  incident_rca_finetune: [{ value: 'qwen_2_5_7b', label: 'Qwen 2.5 7B', params: '7B', hw: 'Gaudi' }, { value: 'llama_3_1_8b', label: 'Llama 3.1 8B', params: '8B', hw: 'Gaudi' }],
  openshift_troubleshooting_finetune: [{ value: 'granite_ops_model', label: 'Granite Ops 3B', params: '3B', hw: 'Gaudi' }],
  dashboard_vision_finetune: [{ value: 'qwen_2_5_vl_7b', label: 'Qwen 2.5 VL 7B', params: '7B', hw: 'Gaudi' }],
  code_failure_finetune: [{ value: 'qwen_2_5_coder_7b', label: 'Qwen 2.5 Coder 7B', params: '7B', hw: 'Gaudi' }],
  small_classifier_tune: [{ value: 'phi_small_utility', label: 'Phi Small 1.5B', params: '1.5B', hw: 'Xeon 6' }],
};

const DATASETS: Record<string, string> = {
  incident_rca_finetune: 'synthetic_incident_rca_v1', openshift_troubleshooting_finetune: 'synthetic_openshift_troubleshooting_v1',
  dashboard_vision_finetune: 'synthetic_dashboard_vision_v1', code_failure_finetune: 'synthetic_code_failure_v1', small_classifier_tune: 'synthetic_small_classifier_v1',
};

type Step = 'select' | 'dataset' | 'training' | 'evaluation' | 'serving';

interface TrainingResult {
  metrics: { train_loss_start: number; train_loss_end: number; training_duration_seconds: number; samples_seen: number };
  evaluation: { base_score: number; tuned_score: number; improvement: number; dimensions: Record<string, { base: number; tuned: number }> };
  loss_curve: number[];
  artifacts: { adapter_ref: string };
  serving_candidate: { status: string; target_lane: string };
  hardware_lane: string;
}

export default function TrainingDemo() {
  const [task, setTask] = useState('incident_rca_finetune');
  const [taskOpen, setTaskOpen] = useState(false);
  const [model, setModel] = useState('qwen_2_5_7b');
  const [step, setStep] = useState<Step>('select');
  const [result, setResult] = useState<TrainingResult | null>(null);
  const [animatedLoss, setAnimatedLoss] = useState<number[]>([]);
  const [loading, setLoading] = useState(false);
  const animRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => { const m = MODELS[task]; if (m?.length) setModel(m[0].value); }, [task]);
  useEffect(() => () => { if (animRef.current) clearInterval(animRef.current); }, []);

  const modelMeta = (MODELS[task] || []).find(m => m.value === model);

  const runTraining = async () => {
    setLoading(true);
    setStep('training');
    setAnimatedLoss([]);
    try {
      const resp = await api.trainingRun(task, model, DATASETS[task], 'mock_lora', 42) as { run_id: string };
      await new Promise(r => setTimeout(r, 500));
      const status = await api.trainingStatus(resp.run_id) as Record<string, unknown>;
      // Wait for completion
      let data = status;
      for (let i = 0; i < 20; i++) {
        if (data.status === 'completed') break;
        await new Promise(r => setTimeout(r, 300));
        data = await api.trainingStatus(resp.run_id) as Record<string, unknown>;
      }
      setResult(data as unknown as TrainingResult);
      // Animate loss curve
      const curve = (data.loss_curve as number[]) || [];
      let idx = 0;
      animRef.current = setInterval(() => {
        idx++;
        setAnimatedLoss(curve.slice(0, idx));
        if (idx >= curve.length) {
          if (animRef.current) clearInterval(animRef.current);
          setTimeout(() => setStep('evaluation'), 500);
        }
      }, 250);
    } catch { setStep('select'); }
    setLoading(false);
  };

  const sampleData = [
    { input: 'Alerts: api-gateway p95 latency above threshold, checkout-service error rate elevated\nLogs: timeout connecting to payment-service, connection pool exhausted', base: 'There appears to be an issue with the checkout service. The latency is high.', tuned: 'Checkout latency caused by payment-service connection pool exhaustion. Pool limit of 50 exceeded. Fix: increase pool to 100, add circuit breaker.' },
    { input: 'Alerts: gaudi-worker-01 GPU memory 97%, inference-gateway p99 > 10s\nLogs: HBM allocation failed for batch-job-7842', base: 'The GPU memory is full and inference is slow.', tuned: 'Gaudi HBM exhaustion by unthrottled batch-job-7842 (94GB/96GB). Routing engine activated Xeon 6 fallback. Fix: terminate job, add resource limits.' },
  ];

  return (
    <>
      <PageSection>
        <Content>
          <Content component="h1">Train + Serve</Content>
          <Content component="p" style={{ maxWidth: '780px', fontSize: '1.05rem' }}>
            Select an open-weight model, see the training data, watch the loss curve converge,
            compare before vs after, and hand off to the inference routing engine.
            All training is simulated — designed to plug into real Intel Gaudi training later.
          </Content>
        </Content>
      </PageSection>

      {/* Step indicator */}
      <PageSection variant="secondary">
        <div style={{ display: 'flex', gap: '0', marginBottom: '16px' }}>
          {(['select', 'dataset', 'training', 'evaluation', 'serving'] as Step[]).map((s, i) => {
            const labels = ['1. Model', '2. Data', '3. Train', '4. Evaluate', '5. Serve'];
            const active = s === step;
            const done = ['select', 'dataset', 'training', 'evaluation', 'serving'].indexOf(step) > i;
            return (
              <div key={s} style={{ display: 'flex', alignItems: 'center' }}>
                <div style={{
                  padding: '6px 14px', borderRadius: '4px', fontSize: '0.78rem', fontWeight: 600,
                  background: active ? 'var(--rh-color--brand)' : done ? 'var(--rh-color--success)' : 'var(--rh-color--surface-secondary)',
                  color: active || done ? '#fff' : 'var(--rh-color--text-secondary)',
                  transition: 'all 0.3s',
                }}>
                  {done ? '✓' : ''} {labels[i]}
                </div>
                {i < 4 && <div style={{ width: '20px', height: '2px', background: done ? 'var(--rh-color--success)' : 'var(--rh-color--border)' }} />}
              </div>
            );
          })}
        </div>
      </PageSection>

      {/* Step 1: Model Selection */}
      {step === 'select' && (
        <PageSection>
          <Content component="h2" style={{ marginBottom: '12px' }}>Select Model & Task</Content>
          <div style={{ display: 'flex', gap: '1rem', flexWrap: 'wrap', marginBottom: '16px' }}>
            <div>
              <div style={{ fontSize: '0.85rem', fontWeight: 600, marginBottom: 4 }}>Training Task</div>
              <Select toggle={(ref) => (<MenuToggle ref={ref} onClick={() => setTaskOpen(!taskOpen)} isExpanded={taskOpen} style={{ width: '240px' }}>{TASKS.find(t => t.value === task)?.label}</MenuToggle>)}
                isOpen={taskOpen} onSelect={(_e, v) => { setTask(v as string); setTaskOpen(false); }} onOpenChange={setTaskOpen} selected={task}>
                {TASKS.map(t => <SelectOption key={t.value} value={t.value} description={t.desc}>{t.label}</SelectOption>)}
              </Select>
            </div>
          </div>

          {modelMeta && (
            <Card style={{ maxWidth: '500px', marginBottom: '16px' }}>
              <CardBody>
                <div style={{ fontWeight: 700, fontSize: '1rem', marginBottom: '4px' }}>{modelMeta.label}</div>
                <div style={{ fontSize: '0.82rem', color: 'var(--rh-color--text-secondary)', marginBottom: '8px' }}>
                  {modelMeta.params} parameters · Training on {modelMeta.hw} · Method: LoRA
                </div>
                <div style={{ fontSize: '0.78rem', display: 'flex', gap: '12px' }}>
                  <Label color={modelMeta.hw === 'Gaudi' ? 'orange' : 'blue'}>{modelMeta.hw}</Label>
                  <Label color="grey">LoRA (~0.5% params trainable)</Label>
                  <Label color="grey">{DATASETS[task]}</Label>
                </div>
              </CardBody>
            </Card>
          )}

          <Button variant="primary" onClick={() => setStep('dataset')}>Next: View Dataset →</Button>
        </PageSection>
      )}

      {/* Step 2: Dataset Preview */}
      {step === 'dataset' && (
        <PageSection>
          <Content component="h2" style={{ marginBottom: '12px' }}>Dataset Preview</Content>
          <Content component="p" style={{ maxWidth: '640px', marginBottom: '16px', color: 'var(--rh-color--text-secondary)' }}>
            The model learns from examples like these. Each sample has an input (alerts + logs) and an expected output (detailed RCA).
          </Content>

          {sampleData.map((s, i) => (
            <Card key={i} style={{ marginBottom: '12px', maxWidth: '700px' }}>
              <CardBody>
                <div style={{ fontSize: '0.78rem', fontWeight: 600, marginBottom: '6px' }}>Sample {i + 1}</div>
                <div style={{ fontSize: '0.82rem', padding: '8px', borderRadius: '4px', background: 'var(--rh-color--surface-secondary)', marginBottom: '8px', whiteSpace: 'pre-wrap', fontFamily: 'var(--pf-t--global--font--family--mono)' }}>
                  {s.input}
                </div>
                <div style={{ fontSize: '0.75rem', fontWeight: 600, color: 'var(--rh-color--text-secondary)', marginBottom: '2px' }}>Expected output:</div>
                <div style={{ fontSize: '0.82rem', padding: '8px', borderRadius: '4px', background: 'var(--rh-color--success-bg)', border: '1px solid var(--rh-color--success)' }}>
                  {s.tuned}
                </div>
              </CardBody>
            </Card>
          ))}

          <div style={{ display: 'flex', gap: '8px' }}>
            <Button variant="secondary" onClick={() => setStep('select')}>← Back</Button>
            <Button variant="primary" onClick={runTraining} isLoading={loading}>Start Training →</Button>
          </div>
        </PageSection>
      )}

      {/* Step 3: Training Progress */}
      {step === 'training' && (
        <PageSection>
          <Content component="h2" style={{ marginBottom: '12px' }}>Training in Progress</Content>
          <div style={{ maxWidth: '500px', padding: '16px', background: 'var(--rh-color--surface-secondary)', borderRadius: '8px', marginBottom: '16px' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '8px' }}>
              <span style={{ fontWeight: 600 }}>
                <Label color={modelMeta?.hw === 'Gaudi' ? 'orange' : 'blue'} isCompact style={{ marginRight: '6px' }}>{modelMeta?.hw}</Label>
                LoRA Training — {modelMeta?.label}
              </span>
              <Label color="blue" isCompact>SIMULATED</Label>
            </div>

            {/* Animated loss curve */}
            <div style={{ fontSize: '0.78rem', fontWeight: 600, marginBottom: '6px' }}>Loss Curve</div>
            <div style={{ display: 'flex', alignItems: 'flex-end', gap: '2px', height: '80px', marginBottom: '8px' }}>
              {animatedLoss.map((loss, i) => {
                const maxLoss = result?.loss_curve ? Math.max(...result.loss_curve) : 2.5;
                return (
                  <div key={i} style={{
                    flex: 1, borderRadius: '2px 2px 0 0',
                    height: `${(loss / maxLoss) * 100}%`,
                    background: i < animatedLoss.length / 2 ? 'var(--rh-color--gaudi)' : 'var(--rh-color--success)',
                    transition: 'height 0.2s',
                  }} />
                );
              })}
            </div>

            {result && (
              <div style={{ fontSize: '0.82rem', display: 'flex', gap: '16px', flexWrap: 'wrap' }}>
                <span>Loss: <strong>{result.metrics.train_loss_start.toFixed(3)} → {result.metrics.train_loss_end.toFixed(3)}</strong></span>
                <span>Samples: <strong>{result.metrics.samples_seen.toLocaleString()}</strong></span>
                <span>Duration: <strong>{result.metrics.training_duration_seconds.toFixed(0)}s</strong></span>
              </div>
            )}
          </div>
        </PageSection>
      )}

      {/* Step 4: Before/After Evaluation */}
      {step === 'evaluation' && result && (
        <PageSection>
          <Content component="h2" style={{ marginBottom: '12px' }}>Before vs After</Content>

          {/* Score cards */}
          <div style={{ display: 'flex', gap: '16px', marginBottom: '16px', flexWrap: 'wrap' }}>
            <Card style={{ flex: '1 1 150px', maxWidth: '200px' }}><CardBody style={{ textAlign: 'center' }}>
              <div style={{ fontSize: '0.72rem', fontWeight: 600, textTransform: 'uppercase', color: 'var(--rh-color--text-secondary)' }}>Base Model</div>
              <div style={{ fontSize: '2rem', fontWeight: 700, color: 'var(--rh-color--brand)' }}>{(result.evaluation.base_score * 100).toFixed(0)}%</div>
            </CardBody></Card>
            <Card style={{ flex: '1 1 150px', maxWidth: '200px', borderTop: '4px solid var(--rh-color--success)' }}><CardBody style={{ textAlign: 'center' }}>
              <div style={{ fontSize: '0.72rem', fontWeight: 600, textTransform: 'uppercase', color: 'var(--rh-color--text-secondary)' }}>Fine-Tuned</div>
              <div style={{ fontSize: '2rem', fontWeight: 700, color: 'var(--rh-color--success)' }}>{(result.evaluation.tuned_score * 100).toFixed(0)}%</div>
            </CardBody></Card>
            <Card style={{ flex: '1 1 150px', maxWidth: '200px' }}><CardBody style={{ textAlign: 'center' }}>
              <div style={{ fontSize: '0.72rem', fontWeight: 600, textTransform: 'uppercase', color: 'var(--rh-color--text-secondary)' }}>Improvement</div>
              <div style={{ fontSize: '2rem', fontWeight: 700, color: 'var(--rh-color--xeon6)' }}>+{(result.evaluation.improvement * 100).toFixed(0)}%</div>
            </CardBody></Card>
          </div>

          {/* Example comparison */}
          <Card style={{ maxWidth: '700px', marginBottom: '16px' }}>
            <CardBody>
              <div style={{ fontSize: '0.78rem', fontWeight: 600, marginBottom: '8px' }}>Example: Same prompt, different model</div>
              <div style={{ fontSize: '0.78rem', padding: '6px 8px', borderRadius: '4px', background: 'var(--rh-color--surface-secondary)', marginBottom: '8px', fontFamily: 'var(--pf-t--global--font--family--mono)' }}>
                {sampleData[0].input.slice(0, 120)}...
              </div>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '8px' }}>
                <div>
                  <div style={{ fontSize: '0.72rem', fontWeight: 600, color: 'var(--rh-color--brand)', marginBottom: '4px' }}>BASE MODEL</div>
                  <div style={{ fontSize: '0.82rem', padding: '8px', borderRadius: '4px', border: '1px solid var(--rh-color--brand)', minHeight: '60px' }}>
                    {sampleData[0].base}
                  </div>
                </div>
                <div>
                  <div style={{ fontSize: '0.72rem', fontWeight: 600, color: 'var(--rh-color--success)', marginBottom: '4px' }}>FINE-TUNED</div>
                  <div style={{ fontSize: '0.82rem', padding: '8px', borderRadius: '4px', border: '1px solid var(--rh-color--success)', background: 'var(--rh-color--success-bg)', minHeight: '60px' }}>
                    {sampleData[0].tuned}
                  </div>
                </div>
              </div>
            </CardBody>
          </Card>

          {/* Score breakdown */}
          {result.evaluation.dimensions && (
            <div style={{ maxWidth: '500px', marginBottom: '16px' }}>
              <div style={{ fontSize: '0.78rem', fontWeight: 600, marginBottom: '6px' }}>Score Breakdown</div>
              {Object.entries(result.evaluation.dimensions).map(([dim, scores]) => (
                <div key={dim} style={{ marginBottom: '6px' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.78rem', marginBottom: '2px' }}>
                    <span style={{ textTransform: 'capitalize' }}>{dim.replace(/_/g, ' ')}</span>
                    <span style={{ fontFamily: 'var(--pf-t--global--font--family--mono)' }}>
                      {(scores.base * 100).toFixed(0)}% → {(scores.tuned * 100).toFixed(0)}%
                    </span>
                  </div>
                  <div style={{ display: 'flex', height: '6px', borderRadius: '3px', overflow: 'hidden', background: 'var(--rh-color--surface-secondary)' }}>
                    <div style={{ width: `${scores.base * 100}%`, background: 'var(--rh-color--brand)', opacity: 0.4 }} />
                    <div style={{ width: `${(scores.tuned - scores.base) * 100}%`, background: 'var(--rh-color--success)' }} />
                  </div>
                </div>
              ))}
            </div>
          )}

          <Button variant="primary" onClick={() => setStep('serving')}>Next: Serving Handoff →</Button>
        </PageSection>
      )}

      {/* Step 5: Serving Handoff */}
      {step === 'serving' && result && (
        <PageSection>
          <Content component="h2" style={{ marginBottom: '12px' }}>Ready to Serve</Content>
          <Content component="p" style={{ maxWidth: '640px', marginBottom: '16px', color: 'var(--rh-color--text-secondary)' }}>
            The fine-tuned adapter is ready to deploy through the existing inference routing engine.
            In production, this would be served on the {result.serving_candidate?.target_lane || result.hardware_lane} lane.
          </Content>

          <div style={{ display: 'flex', gap: '12px', flexWrap: 'wrap', marginBottom: '16px' }}>
            <Card><CardBody>
              <div style={{ fontWeight: 600, marginBottom: '4px' }}>Status</div>
              <Label color="green" style={{ fontSize: '0.88rem' }}>{result.serving_candidate?.status?.toUpperCase() || 'READY'}</Label>
            </CardBody></Card>
            <Card><CardBody>
              <div style={{ fontWeight: 600, marginBottom: '4px' }}>Target Lane</div>
              <Label color={result.serving_candidate?.target_lane?.includes('gaudi') ? 'orange' : 'blue'}>
                {result.serving_candidate?.target_lane || result.hardware_lane}
              </Label>
            </CardBody></Card>
            <Card><CardBody>
              <div style={{ fontWeight: 600, marginBottom: '4px' }}>Adapter</div>
              <div style={{ fontSize: '0.75rem', fontFamily: 'var(--pf-t--global--font--family--mono)' }}>
                {result.artifacts?.adapter_ref || 'N/A'}
              </div>
            </CardBody></Card>
          </div>

          <div style={{
            padding: '12px 16px', borderRadius: '6px', fontSize: '0.82rem',
            background: 'var(--rh-color--xeon6-bg)', border: '1px solid var(--rh-color--xeon6)', marginBottom: '16px', maxWidth: '640px',
          }}>
            This is a simulated training run. In production, the LoRA adapter would be deployed as a
            KServe ServingRuntime on Intel {result.serving_candidate?.target_lane?.includes('gaudi') ? 'Gaudi' : 'Xeon 6'} and served
            through the same routing engine demonstrated in the other demos.
          </div>

          <div style={{ display: 'flex', gap: '8px' }}>
            <Button variant="primary" onClick={() => { setStep('select'); setResult(null); }}>Train Another Model</Button>
          </div>
        </PageSection>
      )}
    </>
  );
}
