import { useState } from 'react';
import {
  PageSection,
  Title,
  Button,
  Modal,
  ModalBody,
  ModalFooter,
  ModalHeader,
  TextInput,
  Label,
  CodeBlock,
  CodeBlockCode,
  Spinner,
  Alert,
  Progress,
  ProgressMeasureLocation,
} from '@patternfly/react-core';
import { Table, Thead, Tr, Th, Tbody, Td } from '@patternfly/react-table';
import { useDecisions, useApproveDecision } from '../api/hooks';

export default function GovernanceAudit() {
  const [approveId, setApproveId] = useState<string | null>(null);
  const [approver, setApprover] = useState('');
  const [evidenceId, setEvidenceId] = useState<string | null>(null);

  const { data, isLoading, isError } = useDecisions();
  const approveMutation = useApproveDecision();

  if (isLoading) return <PageSection><Spinner aria-label="Loading" /></PageSection>;
  if (isError) return (
    <PageSection>
      <Title headingLevel="h1" size="xl">Governance Audit Trail</Title>
      <Alert variant="warning" title="No governance data available" style={{ marginTop: '1rem' }}>
        Run a workflow with governance or policy steps (AIOps Copilot or Governed Agent) to generate audit entries.
      </Alert>
    </PageSection>
  );

  const selectedDecision = data?.data.find((d) => d.id === evidenceId);

  if (!data?.data.length) return (
    <PageSection>
      <Title headingLevel="h1" size="xl">Governance Audit Trail</Title>
      <Alert variant="info" title="No governance decisions yet" style={{ marginTop: '1rem' }}>
        AI-generated actions need approval. Run a governed workflow (AIOps Copilot or Governed Agent)
        from the Try It page to see how every decision is logged, risk-scored, and approved before execution.
      </Alert>
    </PageSection>
  );

  return (
    <PageSection>
      <Title headingLevel="h1" size="xl">Governance Audit Trail</Title>
      <Table aria-label="Governance decisions" variant="compact">
        <Thead>
          <Tr>
            <Th>Time</Th>
            <Th>Source</Th>
            <Th>Intent</Th>
            <Th>Risk</Th>
            <Th>Decision</Th>
            <Th>Approved By</Th>
            <Th>Actions</Th>
          </Tr>
        </Thead>
        <Tbody>
          {data?.data.map((dec) => (
            <Tr key={dec.id}>
              <Td>{new Date(dec.created_at).toLocaleString()}</Td>
              <Td>{dec.source}</Td>
              <Td>{dec.intent}</Td>
              <Td>
                <Progress
                  value={dec.risk_score * 100}
                  title={dec.risk_level}
                  measureLocation={ProgressMeasureLocation.inside}
                  style={{ width: '120px' }}
                />
              </Td>
              <Td>
                <Label color={dec.decision === 'deny' ? 'red' : dec.decision === 'escalate' ? 'orange' : 'green'}>
                  {dec.decision}
                </Label>
              </Td>
              <Td>{dec.approved_by || '—'}</Td>
              <Td>
                <Button variant="link" onClick={() => setEvidenceId(dec.id)} size="sm">Evidence</Button>
                {!dec.approved_by && dec.decision !== 'deny' && (
                  <Button variant="secondary" onClick={() => setApproveId(dec.id)} size="sm" style={{ marginLeft: '0.5rem' }}>
                    Approve
                  </Button>
                )}
              </Td>
            </Tr>
          ))}
        </Tbody>
      </Table>

      {approveId && (
        <Modal
          isOpen
          onClose={() => setApproveId(null)}
          aria-label="Approve decision"
          variant="small"
        >
          <ModalHeader title="Approve Governance Decision" />
          <ModalBody>
            <TextInput
              value={approver}
              onChange={(_e, val) => setApprover(val)}
              aria-label="Approver name"
              placeholder="Your name"
            />
          </ModalBody>
          <ModalFooter>
            <Button
              variant="primary"
              isDisabled={!approver}
              onClick={() => {
                approveMutation.mutate({ id: approveId, approvedBy: approver });
                setApproveId(null);
                setApprover('');
              }}
            >
              Approve
            </Button>
            <Button variant="link" onClick={() => setApproveId(null)}>Cancel</Button>
          </ModalFooter>
        </Modal>
      )}

      {evidenceId && selectedDecision && (
        <Modal isOpen onClose={() => setEvidenceId(null)} aria-label="Evidence" variant="medium">
          <ModalHeader title={`Evidence: ${selectedDecision.intent}`} />
          <ModalBody>
            <p><strong>Decision:</strong> {selectedDecision.decision}</p>
            <p><strong>Reason:</strong> {selectedDecision.reason}</p>
            <p><strong>Risk:</strong> {selectedDecision.risk_level} ({selectedDecision.risk_score})</p>
            <CodeBlock>
              <CodeBlockCode>{JSON.stringify(selectedDecision.evidence, null, 2)}</CodeBlockCode>
            </CodeBlock>
          </ModalBody>
          <ModalFooter>
            <Button variant="link" onClick={() => setEvidenceId(null)}>Close</Button>
          </ModalFooter>
        </Modal>
      )}
    </PageSection>
  );
}
