import { Component, type ErrorInfo, type ReactNode } from 'react'

interface ModelBoundaryProps {
  children: ReactNode
  fallback: ReactNode
  onFailure: () => void
}

interface ModelBoundaryState {
  failed: boolean
}

export class ModelBoundary extends Component<ModelBoundaryProps, ModelBoundaryState> {
  state: ModelBoundaryState = { failed: false }

  static getDerivedStateFromError(): ModelBoundaryState {
    return { failed: true }
  }

  componentDidCatch(_error: Error, _info: ErrorInfo) {
    this.props.onFailure()
  }

  render() {
    return this.state.failed ? this.props.fallback : this.props.children
  }
}

