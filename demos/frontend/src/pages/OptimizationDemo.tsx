import { Content, Card, CardBody, Label, PageSection } from '@patternfly/react-core';

const METHODS = [
  { name: 'LoRA', full: 'Low-Rank Adaptation', params: '~0.5%', paramsEx: '~35M for 7B', memory: '~16 GB', time: '~20 min', quality: 'Near-full', color: 'green' as const,
    desc: 'Trains small adapter matrices that merge with the base model. Fast, memory-efficient, production-ready. The go-to method for adapting models to specific domains.' },
  { name: 'Full SFT', full: 'Supervised Fine-Tuning', params: '100%', paramsEx: '7B', memory: '~60 GB', time: '~2 hours', quality: 'Highest', color: 'blue' as const,
    desc: 'Updates all model weights. Maximum quality but requires the full model in GPU memory. Best for large datasets and research where quality is paramount.' },
  { name: 'QLoRA', full: 'Quantized LoRA', params: '~0.5%', paramsEx: '~35M for 7B', memory: '~8 GB', time: '~25 min', quality: 'Good', color: 'orange' as const,
    desc: 'LoRA on a 4-bit quantized base model. Fits in significantly less memory with minimal quality loss. Ideal for memory-constrained environments.' },
];

const HW = [
  { name: 'Intel Xeon 6', color: '#0068b5', memory: '256 GB DDR5', lora: '~4 hours', sft: 'Not viable', best: 'Small models (≤3B), inference serving, evaluation',
    why: 'No GPU required. Train lightweight classifiers and utility models on the same hardware that serves them. AMX acceleration helps with INT8/BF16 operations.' },
  { name: 'Intel Gaudi 2', color: '#e67e22', memory: '96 GB HBM2E', lora: '~20 minutes', sft: '~2 hours', best: 'All serious training — 7B to 70B models',
    why: 'High-bandwidth memory enables large batch sizes. 24 tensor cores optimized for training throughput. 12x faster than CPU for LoRA on 7B models.' },
];

export default function OptimizationDemo() {
  return (
    <>
      <PageSection>
        <Content>
          <Content component="h1">Training Optimization</Content>
          <Content component="p" style={{ maxWidth: '780px', fontSize: '1.05rem' }}>
            Not all fine-tuning is the same. The method you choose determines how much memory you need,
            how long training takes, and what quality you get. The hardware you train on determines
            whether it takes minutes or hours.
          </Content>
        </Content>
      </PageSection>

      {/* Method Comparison */}
      <PageSection variant="secondary">
        <Content component="h2" style={{ marginBottom: '12px' }}>Training Methods Compared</Content>
        <Content component="p" style={{ maxWidth: '640px', marginBottom: '16px', color: 'var(--rh-color--text-secondary)' }}>
          For a 7B parameter model, these are the tradeoffs. LoRA is the sweet spot for most
          production use cases — near-full quality at a fraction of the memory and time.
        </Content>

        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: '12px', marginBottom: '16px' }}>
          {METHODS.map(m => (
            <Card key={m.name} isFullHeight>
              <CardBody>
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '8px' }}>
                  <Label color={m.color} style={{ fontSize: '0.88rem', padding: '4px 12px' }}>{m.name}</Label>
                  <span style={{ fontSize: '0.75rem', color: 'var(--rh-color--text-secondary)' }}>{m.full}</span>
                </div>
                <div style={{ fontSize: '0.82rem', color: 'var(--rh-color--text-secondary)', marginBottom: '12px', lineHeight: '1.5' }}>
                  {m.desc}
                </div>
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '6px', fontSize: '0.82rem' }}>
                  <div><strong>Trainable:</strong> {m.params} ({m.paramsEx})</div>
                  <div><strong>Memory:</strong> {m.memory}</div>
                  <div><strong>Time (7B on Gaudi):</strong> {m.time}</div>
                  <div><strong>Quality:</strong> {m.quality}</div>
                </div>
              </CardBody>
            </Card>
          ))}
        </div>

        {/* Visual comparison bars */}
        <Card style={{ maxWidth: '600px' }}>
          <CardBody>
            <div style={{ fontSize: '0.82rem', fontWeight: 600, marginBottom: '10px' }}>Memory Footprint (7B model on Gaudi)</div>
            {METHODS.map(m => {
              const memGB = parseInt(m.memory);
              const maxMem = 60;
              return (
                <div key={m.name} style={{ marginBottom: '8px' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.78rem', marginBottom: '2px' }}>
                    <span>{m.name}</span>
                    <span style={{ fontFamily: 'var(--pf-t--global--font--family--mono)' }}>{m.memory}</span>
                  </div>
                  <div style={{ height: '8px', borderRadius: '4px', background: 'var(--rh-color--surface-secondary)', overflow: 'hidden' }}>
                    <div style={{ height: '100%', width: `${(memGB / maxMem) * 100}%`, background: m.color === 'green' ? 'var(--rh-color--success)' : m.color === 'blue' ? 'var(--rh-color--xeon6)' : 'var(--rh-color--gaudi)', borderRadius: '4px' }} />
                  </div>
                </div>
              );
            })}
            <div style={{ fontSize: '0.72rem', color: 'var(--rh-color--text-secondary)', marginTop: '6px' }}>
              Intel Gaudi 2 has 96 GB HBM — all three methods fit comfortably.
            </div>
          </CardBody>
        </Card>
      </PageSection>

      {/* Hardware Comparison */}
      <PageSection>
        <Content component="h2" style={{ marginBottom: '12px' }}>Hardware for Training</Content>
        <Content component="p" style={{ maxWidth: '640px', marginBottom: '16px', color: 'var(--rh-color--text-secondary)' }}>
          Xeon 6 handles small model training and all inference serving. Gaudi handles everything
          else — 12x faster for LoRA on 7B models. The platform routes trained models back to the
          right hardware for serving.
        </Content>

        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(340px, 1fr))', gap: '12px', marginBottom: '16px' }}>
          {HW.map(h => (
            <Card key={h.name} isFullHeight style={{ borderTop: `4px solid ${h.color}` }}>
              <CardBody>
                <div style={{ fontWeight: 700, fontSize: '1rem', marginBottom: '4px' }}>{h.name}</div>
                <div style={{ fontSize: '0.82rem', color: 'var(--rh-color--text-secondary)', marginBottom: '12px', lineHeight: '1.5' }}>{h.why}</div>
                <div style={{ fontSize: '0.82rem', display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '6px' }}>
                  <div><strong>Memory:</strong> {h.memory}</div>
                  <div><strong>Best for:</strong> {h.best}</div>
                  <div><strong>7B LoRA:</strong> {h.lora}</div>
                  <div><strong>7B Full SFT:</strong> {h.sft}</div>
                </div>
              </CardBody>
            </Card>
          ))}
        </div>

        {/* Speed comparison */}
        <Card style={{ maxWidth: '600px' }}>
          <CardBody>
            <div style={{ fontSize: '0.82rem', fontWeight: 600, marginBottom: '10px' }}>LoRA Training Speed — 7B Model</div>
            {[
              { name: 'Intel Xeon 6 (CPU)', time: 240, label: '~4 hours', color: '#0068b5' },
              { name: 'Intel Gaudi 2 (GPU)', time: 20, label: '~20 minutes', color: '#e67e22' },
            ].map(h => (
              <div key={h.name} style={{ marginBottom: '8px' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.78rem', marginBottom: '2px' }}>
                  <span>{h.name}</span>
                  <span style={{ fontFamily: 'var(--pf-t--global--font--family--mono)', fontWeight: 700 }}>{h.label}</span>
                </div>
                <div style={{ height: '8px', borderRadius: '4px', background: 'var(--rh-color--surface-secondary)', overflow: 'hidden' }}>
                  <div style={{ height: '100%', width: `${(h.time / 240) * 100}%`, background: h.color, borderRadius: '4px' }} />
                </div>
              </div>
            ))}
            <div style={{ fontSize: '0.72rem', color: 'var(--rh-color--text-secondary)', marginTop: '6px' }}>
              Gaudi is 12x faster. After training, the model serves through the same routing engine — small tasks on Xeon 6, heavy generation on Gaudi.
            </div>
          </CardBody>
        </Card>
      </PageSection>

      {/* When to Use What */}
      <PageSection variant="secondary">
        <Content component="h2" style={{ marginBottom: '12px' }}>When to Use What</Content>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: '12px' }}>
          {[
            { title: 'LoRA on Gaudi', when: 'Most production use cases', examples: 'Adapt a 7B model to your incident data in 20 minutes. Deploy the adapter alongside the base model. Fast iteration, minimal risk.', color: 'green' as const },
            { title: 'Full SFT on Gaudi', when: 'Maximum quality, large datasets', examples: 'Train on 100K+ samples when quality is critical. Research and experimentation. Produces a standalone model checkpoint.', color: 'blue' as const },
            { title: 'QLoRA on Gaudi', when: 'Memory-constrained or edge', examples: 'Fit training into less memory. Deploy quantized models on smaller hardware. Good for edge inference or cost optimization.', color: 'orange' as const },
            { title: 'Small model on Xeon 6', when: 'Lightweight classifiers', examples: 'Train a 1.5B classifier for alert triage or request routing. Runs on the same CPU that serves it — no GPU needed for training or inference.', color: 'grey' as const },
          ].map(c => (
            <Card key={c.title}><CardBody>
              <Label color={c.color} style={{ marginBottom: '8px' }}>{c.title}</Label>
              <div style={{ fontWeight: 600, fontSize: '0.82rem', marginBottom: '4px' }}>{c.when}</div>
              <div style={{ fontSize: '0.78rem', color: 'var(--rh-color--text-secondary)', lineHeight: '1.5' }}>{c.examples}</div>
            </CardBody></Card>
          ))}
        </div>
      </PageSection>
    </>
  );
}
