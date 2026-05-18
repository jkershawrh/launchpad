import {
  Card,
  CardBody,
  CardTitle,
  Gallery,
  GalleryItem,
  Label,
  PageSection,
  
  Content,
  List,
  ListItem,
} from '@patternfly/react-core';

const sections = [
  {
    title: 'Getting Started',
    color: 'red' as const,
    items: [
      { label: 'Platform README', desc: 'Project overview, structure, and current status', path: 'README.md' },
      { label: 'CPU Quickstart', desc: 'Deploy CPU inference on Xeon 6 in 5 minutes', path: 'docs/quickstarts/cpu-hello-world/README.md' },
      { label: 'Gaudi Quickstart', desc: 'Deploy Gaudi GPU inference with decision guide', path: 'docs/quickstarts/gaudi-hello-world/README.md' },
      { label: 'Cluster Discovery', desc: 'Discover cluster capabilities, nodes, and operators', path: 'scripts/discover-cluster.sh' },
    ],
  },
  {
    title: 'Architecture',
    color: 'red' as const,
    items: [
      { label: 'Golden Paths', desc: 'Validated deployment paths for CPU and Gaudi', path: 'docs/architecture/golden-paths.md' },
      { label: 'Stakeholder Map', desc: 'Responsibility matrix: Partner, Red Hat, Intel, Rackspace', path: 'docs/architecture/stakeholder-map.md' },
      { label: 'CPU Manifests', desc: 'KServe deployment details for Xeon 6 path', path: 'deploy/cpu-inference/README.md' },
      { label: 'Gaudi Manifests', desc: 'KServe deployment details for Gaudi path', path: 'deploy/gaudi-inference/README.md' },
    ],
  },
  {
    title: 'Routing Engine',
    color: 'orange' as const,
    items: [
      { label: 'Overdrive Engine', desc: 'Rubric-based lane evaluation — eco, performance, overdrive', path: 'gateway/overdrive/' },
      { label: 'Routing Config', desc: 'Backend definitions, route rules, and task-to-lane mapping', path: 'gateway/config.yaml' },
      { label: 'Routing Policy', desc: 'Policy engine for task classification and backend selection', path: 'gateway/routing_policy.py' },
      { label: 'Overdrive Rubrics', desc: 'Check definitions for endpoint health, token limits, and priority gates', path: 'gateway/overdrive/rubrics/' },
    ],
  },
  {
    title: 'API Reference',
    color: 'grey' as const,
    items: [
      { label: 'Gateway API Docs', desc: 'FastAPI auto-generated interactive documentation', path: '/docs', external: true },
      { label: 'Routing Endpoints', desc: 'POST /v1/route — route a request to the correct Intel hardware tier' },
      { label: 'Overdrive Endpoints', desc: 'POST /v1/overdrive/route, /batch, /status, /health — lane evaluation and batch routing' },
      { label: 'Analytics Endpoints', desc: 'Cost summary, latency percentiles, routing distribution across Xeon 6 and Gaudi' },
      { label: 'Governance Endpoints', desc: 'Decision history, approval workflow, risk scoring, and evidence bundles' },
    ],
  },
  {
    title: 'Cluster Deployment',
    color: 'blue' as const,
    items: [
      { label: 'Platform Manifests', desc: 'Kustomize base for the full platform — gateway, frontend, postgres', path: 'deploy/cluster/' },
      { label: 'Database Deploy', desc: 'PostgreSQL deployment, PVC, secrets, and network policy', path: 'deploy/database/' },
      { label: 'Observability', desc: 'Prometheus ServiceMonitor and Grafana dashboard', path: 'deploy/observability/' },
      { label: 'GitOps', desc: 'ArgoCD Application definition for continuous deployment', path: 'deploy/gitops/' },
    ],
  },
  {
    title: 'Automation',
    color: 'grey' as const,
    items: [
      { label: 'Ansible Playbooks', desc: 'deploy-platform.yaml — full stack deployment with role-based stages', path: 'ansible/playbooks/' },
      { label: 'Build Script', desc: 'Container build and push for CPU, Gaudi, and gateway images', path: 'scripts/build-images.sh' },
      { label: 'Podman Compose', desc: 'Local development stack with PostgreSQL, gateway, and frontend', path: 'podman-compose.yaml' },
      { label: 'Model Export', desc: 'Export and cache models for offline deployment', path: 'scripts/export-models.sh' },
    ],
  },
  {
    title: 'Demo Applications',
    color: 'teal' as const,
    items: [
      { label: 'Enterprise RAG', desc: 'Embed → search → rerank → generate pipeline across Xeon 6 and Gaudi', path: 'pocs/enterprise-rag/' },
      { label: 'AIOps Copilot', desc: 'Alert classification → RCA → governed action with hardware-aware routing', path: 'pocs/aiops-copilot/' },
      { label: 'Governed Agent', desc: 'Intent → risk → plan → policy validation with Granite on Xeon 6', path: 'pocs/governed-agent/' },
    ],
  },
];

export default function Docs() {
  return (
    <>
      <PageSection>
        <Content>
          <Content component={"h1"}>Documentation</Content>
          <Content component={"p"} style={{ maxWidth: '720px' }}>
            Learn how the platform works. Deploy it on your own cluster. Extend it with your
            own models, routing rules, and workload profiles. Start with the CPU quickstart
            for Xeon 6 or the Gaudi quickstart for large model inference.
          </Content>
        </Content>
      </PageSection>

      <PageSection>
        <Gallery hasGutter minWidths={{ default: '380px' }}>
          {sections.map((section) => (
            <GalleryItem key={section.title}>
              <Card isFullHeight>
                <CardTitle>
                  <Label color={section.color} style={{ marginRight: '0.5rem' }}>{section.title}</Label>
                </CardTitle>
                <CardBody>
                  <Content>
                    <List>
                      {section.items.map((item) => (
                        <ListItem key={item.label}>
                          <strong>{item.label}</strong>
                          <br />
                          <Content component={"small"} style={{ color: 'var(--pf-t--global--text--color--subtle)' }}>
                            {item.desc}
                          </Content>
                          {item.path && (
                            <Content component="small" style={{ fontFamily: 'var(--pf-t--global--font--family--mono)', display: 'block' }}>
                              {item.path.startsWith('/') ? (
                                <a href={item.path} target="_blank" rel="noopener noreferrer">{item.path}</a>
                              ) : (
                                <span style={{ color: 'var(--pf-t--global--text--color--subtle)' }}>{item.path}</span>
                              )}
                            </Content>
                          )}
                        </ListItem>
                      ))}
                    </List>
                  </Content>
                </CardBody>
              </Card>
            </GalleryItem>
          ))}
        </Gallery>
      </PageSection>
    </>
  );
}
