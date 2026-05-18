import { useState } from 'react';
import {
  PageSection,
  Content,
  Tabs,
  Tab,
  TabTitleText,
  Card,
  CardBody,
  Gallery,
  GalleryItem,
  Label,
} from '@patternfly/react-core';
import LiveWorkflow, { type WorkflowStep } from '../components/LiveWorkflow';
import BuildYourOwn from '../components/BuildYourOwn';
import HardwareBadge from '../components/HardwareBadge';

interface Prompt {
  label: string;
  text: string;
  description: string;
}

interface WorkflowScenario {
  key: string;
  title: string;
  subtitle: string;
  message: string;
  steps: WorkflowStep[];
  prompts: Prompt[];
}

const scenarios: WorkflowScenario[] = [
  {
    key: 'rag',
    title: 'Enterprise RAG',
    subtitle: 'Embed → Search → Rerank → Generate',
    message: 'Embedding, search, and reranking are fast — Xeon 6 handles them cheaply. Gaudi only activates for the generation step, where large model throughput matters.',
    steps: [
      { label: 'Embed Query', hw: 'xeon6', task: 'embeddings' },
      { label: 'Vector Search', hw: 'xeon6', task: 'search' },
      { label: 'Rerank Candidates', hw: 'xeon6', task: 'reranking' },
      { label: 'Generate Answer', hw: 'gaudi', task: 'completion', model_size_b: 17 },
    ],
    prompts: [
      { label: 'Technical question', text: 'How does Intel Xeon 6 accelerate AI inference with AMX?', description: 'Multi-step RAG pipeline' },
      { label: 'Product question', text: 'What is OpenShift AI and how does it serve models?', description: 'Knowledge retrieval + generation' },
      { label: 'Architecture question', text: 'How does KServe compare to direct model deployment on Kubernetes?', description: 'Complex reasoning from context' },
    ],
  },
  {
    key: 'aiops',
    title: 'AIOps Copilot',
    subtitle: 'Classify → Correlate → Analyze → Validate',
    message: 'From alert to governed action in under 3 seconds.',
    steps: [
      { label: 'Classify Severity', hw: 'xeon6', task: 'classification' },
      { label: 'Find Similar Incidents', hw: 'xeon6', task: 'embeddings' },
      { label: 'Generate RCA', hw: 'gaudi', task: 'completion', model_size_b: 17 },
      { label: 'Governance Gate', hw: 'xeon6', task: 'governance' },
    ],
    prompts: [
      { label: 'Latency alert', text: 'High latency on inference gateway pods, p99 > 5s for last 10 minutes', description: 'Classify → correlate → RCA → govern' },
      { label: 'OOM alert', text: 'Pod OOM kills in gaudi-inference namespace, 3 restarts in 5 minutes', description: 'Memory incident pipeline' },
      { label: 'Certificate alert', text: 'SSL certificate on model serving route expires in 24 hours', description: 'Security incident pipeline' },
    ],
  },
  {
    key: 'agent',
    title: 'Governed Agent',
    subtitle: 'Intent → Risk → Plan → Policy',
    message: 'Every action is classified, risk-scored, planned, and policy-checked.',
    steps: [
      { label: 'Classify Intent', hw: 'xeon6', task: 'classification' },
      { label: 'Score Risk', hw: 'xeon6', task: 'classification' },
      { label: 'Generate Plan', hw: 'gaudi', task: 'completion', model_size_b: 17 },
      { label: 'Policy Check', hw: 'xeon6', task: 'policy' },
    ],
    prompts: [
      { label: 'Safe action', text: 'Read the logs from the inference gateway pods', description: 'Low risk → auto-approved' },
      { label: 'Risky action', text: 'Restart the inference pods in the production gaudi namespace', description: 'Medium risk → escalated' },
      { label: 'Blocked action', text: 'Delete the production namespace and all resources', description: 'Critical risk → denied' },
    ],
  },
];

export default function TryIt() {
  const [activeTab, setActiveTab] = useState(0);
  const [selectedPrompt, setSelectedPrompt] = useState<Prompt | null>(null);
  const [runTrigger, setRunTrigger] = useState(0);

  const scenario = scenarios[activeTab];

  return (
    <>
      <PageSection>
        <Content>
          <Content component="h1">Try It Live</Content>
          <Content component="p" style={{ maxWidth: '720px' }}>
            Pick a workflow and click a scenario. Watch each step route to the Intel hardware
            best suited for it — Xeon 6 for fast, cheap tasks and Gaudi for heavy generation.
            You'll see actual latency, cost, and the routing engine's reasoning.
          </Content>
        </Content>
      </PageSection>

      <PageSection variant="secondary">
        <Tabs
          activeKey={activeTab}
          onSelect={(_e, key) => { setActiveTab(key as number); setSelectedPrompt(null); }}
          aria-label="Workflow scenarios"
        >
          <Tab key="rag" eventKey={0} title={<TabTitleText>Enterprise RAG</TabTitleText>} />
          <Tab key="aiops" eventKey={1} title={<TabTitleText>AIOps Copilot</TabTitleText>} />
          <Tab key="agent" eventKey={2} title={<TabTitleText>Governed Agent</TabTitleText>} />
          <Tab key="custom" eventKey={3} title={<TabTitleText>Build Your Own</TabTitleText>} />
        </Tabs>

        {activeTab === scenarios.length ? (
          <div style={{ marginTop: '1.5rem' }}>
            <BuildYourOwn />
          </div>
        ) : (
        <>
        <div style={{ marginTop: '1rem', marginBottom: '1rem' }}>
          <Content component="p" style={{ fontStyle: 'italic', maxWidth: '600px' }}>
            {scenario.message}
          </Content>
        </div>

        <Content component="h3">Select a scenario:</Content>
        <Gallery hasGutter minWidths={{ default: '240px' }} style={{ marginTop: '0.5rem', marginBottom: '1.5rem' }}>
          {scenario.prompts.map((prompt) => (
            <GalleryItem key={prompt.label}>
              <Card
                isClickable isSelectable
                isSelected={selectedPrompt?.label === prompt.label}
                onClick={() => { setSelectedPrompt(prompt); setRunTrigger(t => t + 1); }}
                style={{ cursor: 'pointer' }}
              >
                <CardBody>
                  <div style={{ fontWeight: 600, marginBottom: '4px' }}>{prompt.label}</div>
                  <Content component="small" style={{ display: 'block', color: 'var(--pf-t--global--text--color--subtle)' }}>
                    {prompt.description}
                  </Content>
                  <div style={{
                    marginTop: '8px', fontSize: '0.82rem',
                    fontFamily: 'var(--pf-t--global--font--family--mono)',
                    color: 'var(--pf-t--global--text--color--subtle)',
                  }}>
                    "{prompt.text.length > 80 ? prompt.text.slice(0, 80) + '...' : prompt.text}"
                  </div>
                </CardBody>
              </Card>
            </GalleryItem>
          ))}
        </Gallery>
        </>
        )}
      </PageSection>

      {activeTab < scenarios.length && (
      <PageSection>
        <div style={{ display: 'flex', gap: '2rem', flexWrap: 'wrap' }}>
          <div style={{ flex: '1 1 500px' }}>
            <LiveWorkflow
              key={scenario.key}
              title={scenario.title}
              subtitle={scenario.subtitle}
              steps={scenario.steps}
              prompt={selectedPrompt?.text || scenario.prompts[0].text}
              runTrigger={runTrigger}
            />
          </div>

          <div style={{ flex: '1 1 280px' }}>
            <Content component="h3">How It Works</Content>
            <div style={{ marginTop: '0.5rem' }}>
              {scenario.steps.map((step, i) => (
                <div key={i} style={{ display: 'flex', alignItems: 'center', gap: '8px', padding: '6px 0' }}>
                  <Label isCompact>{i + 1}</Label>
                  <span style={{ fontSize: '0.88rem' }}>{step.label}</span>
                  <HardwareBadge accelerator={step.hw} />
                </div>
              ))}
            </div>
            <Content component="small" style={{ display: 'block', marginTop: '1rem', color: 'var(--pf-t--global--text--color--subtle)' }}>
              Each step makes a real call to the inference gateway.
              The gateway selects the backend based on task type and model size.
              Actual latency is measured end-to-end.
            </Content>
          </div>
        </div>
      </PageSection>
      )}
    </>
  );
}
