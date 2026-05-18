import { useNavigate } from 'react-router-dom';
import {
  Button,
  Card,
  CardBody,
  CardTitle,
  Gallery,
  GalleryItem,
  Label,
  PageSection,
  Split,
  SplitItem,
  
  Content,
} from '@patternfly/react-core';
import { ArrowRightIcon } from '@patternfly/react-icons';
import { useHealth } from '../api/hooks';

export default function Overview() {
  const navigate = useNavigate();
  const health = useHealth();

  return (
    <>
      <PageSection style={{ background: 'var(--pf-t--global--background--color--primary--default)', paddingBottom: '2rem' }}>
        <Content>
          <Content component={"h1"} style={{ fontSize: '2rem', marginBottom: '0.5rem' }}>
            Enterprise AI Inference Platform
          </Content>
          <Content component={"p"} style={{ fontSize: '1.15rem', maxWidth: '720px', color: 'var(--pf-t--global--text--color--subtle)' }}>
            Intel Xeon 6 handles fast, small AI tasks cheaply. Intel Gaudi powers large models
            at scale. One gateway decides which hardware runs each request — and explains every decision.
          </Content>
          <Split hasGutter style={{ marginTop: '1.5rem' }}>
            <SplitItem>
              <Button variant="primary" size="lg" onClick={() => navigate('/try-it')}>
                Try It Live <ArrowRightIcon style={{ marginLeft: '0.5rem' }} />
              </Button>
            </SplitItem>
            <SplitItem>
              <Button variant="secondary" size="lg" onClick={() => navigate('/architecture')}>
                See How It Works
              </Button>
            </SplitItem>
            <SplitItem style={{ marginLeft: '1rem', display: 'flex', alignItems: 'center' }}>
              <Label color={health.data?.status === 'healthy' ? 'green' : 'yellow'}>
                {health.data?.status === 'healthy' ? 'Platform Online' : 'Connecting...'}
              </Label>
            </SplitItem>
          </Split>
        </Content>
      </PageSection>

      <PageSection>
        <Gallery hasGutter minWidths={{ default: '320px' }}>
          <GalleryItem>
            <Card isFullHeight>
              <CardTitle>
                <Label color="blue" style={{ marginRight: '0.5rem' }}>Xeon 6</Label>
                Scale
              </CardTitle>
              <CardBody>
                <Content>
                  <Content component={"p"}>
                    Embeddings, classification, and reranking run on Intel Xeon 6 with AMX
                    (Advanced Matrix Extensions) — hardware-accelerated matrix operations that make
                    AI inference 5-10x faster than standard CPUs, at a fraction of GPU cost.
                  </Content>
                  <Content component={"small"} style={{ color: 'var(--pf-t--global--text--color--subtle)' }}>
                    $0.001–0.002 per 1K tokens &bull; &lt;10ms latency &bull; Models up to 8B parameters
                  </Content>
                </Content>
              </CardBody>
            </Card>
          </GalleryItem>

          <GalleryItem>
            <Card isFullHeight>
              <CardTitle>
                <Label color="orange" style={{ marginRight: '0.5rem' }}>Gaudi</Label>
                Power
              </CardTitle>
              <CardBody>
                <Content>
                  <Content component={"p"}>
                    Large language models (17B+ parameters) need GPU memory bandwidth. Intel Gaudi
                    delivers 100+ tokens/sec generation with 96GB HBM — 10-20x faster than CPU for
                    tasks that demand sustained token generation.
                  </Content>
                  <Content component={"small"} style={{ color: 'var(--pf-t--global--text--color--subtle)' }}>
                    $0.001 per 1K tokens &bull; &lt;2s TTFT &bull; Models 8B–70B+ parameters
                  </Content>
                </Content>
              </CardBody>
            </Card>
          </GalleryItem>

          <GalleryItem>
            <Card isFullHeight>
              <CardTitle>
                <Label color="red" style={{ marginRight: '0.5rem' }}>OpenShift AI</Label>
                Operations
              </CardTitle>
              <CardBody>
                <Content>
                  <Content component={"p"}>
                    One API, smart decisions. The gateway evaluates task type, model size, and
                    priority to route each request. Every decision is logged with full evidence —
                    cost, latency, and reasoning.
                  </Content>
                  <Content component={"small"} style={{ color: 'var(--pf-t--global--text--color--subtle)' }}>
                    {health.data?.routes || '—'} routing rules &bull; Policy enforcement &bull; Every decision logged
                  </Content>
                </Content>
              </CardBody>
            </Card>
          </GalleryItem>
        </Gallery>
      </PageSection>

      <PageSection variant="secondary">
        <Content>
          <Content component={"h2"}>The Demo Story</Content>
          <Content component={"p"} style={{ maxWidth: '720px' }}>
            Enterprise AI isn't one model on one GPU. It's a pipeline — embeddings, search,
            reranking, generation, governance — where each step has different hardware needs. This
            platform routes each step to the right Intel hardware, proves the cost savings, and
            provides full decision transparency. That's what makes Intel + Red Hat credible.
          </Content>
        </Content>
        <Gallery hasGutter minWidths={{ default: '250px' }} style={{ marginTop: '1rem' }}>
          {[
            { num: '1', title: 'See the Architecture', desc: 'Understand the routing logic and Intel hardware tiers.', path: '/architecture' },
            { num: '2', title: 'Explore the Routing Engine', desc: 'Learn the 3 lanes. Route a request. See exactly why Xeon 6 or Gaudi was chosen.', path: '/overdrive' },
            { num: '3', title: 'Try It Live', desc: 'Watch RAG, AIOps, and Agent workflows use intelligent routing in real time.', path: '/try-it' },
            { num: '4', title: 'Run at Scale', desc: 'Simulate 25 to 1,000 enterprise requests and see hardware distribution.', path: '/workload' },
          ].map((step) => (
            <GalleryItem key={step.num}>
              <Card isClickable isSelectable onClick={() => navigate(step.path)}>
                <CardTitle>
                  <Label style={{ marginRight: '0.5rem' }}>{step.num}</Label>
                  {step.title}
                </CardTitle>
                <CardBody>
                  <Content component={"p"}>{step.desc}</Content>
                </CardBody>
              </Card>
            </GalleryItem>
          ))}
        </Gallery>
      </PageSection>
    </>
  );
}
