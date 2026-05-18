import React, { Component, type ReactNode } from 'react';
import { Alert, PageSection, Content, Button } from '@patternfly/react-core';

interface Props { children: ReactNode; }
interface State { hasError: boolean; error: Error | null; }

export default class ErrorBoundary extends Component<Props, State> {
  state: State = { hasError: false, error: null };

  static getDerivedStateFromError(error: Error) {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, info: React.ErrorInfo) {
    console.error('ErrorBoundary caught:', error, info.componentStack);
  }

  render() {
    if (this.state.hasError) {
      return (
        <PageSection>
          <Alert variant="danger" title="Something went wrong">
            <Content component="p">{this.state.error?.message}</Content>
            <Button variant="link" onClick={() => this.setState({ hasError: false, error: null })}>
              Try again
            </Button>
          </Alert>
        </PageSection>
      );
    }
    return this.props.children;
  }
}
