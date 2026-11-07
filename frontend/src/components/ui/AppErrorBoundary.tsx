import { Component, type ErrorInfo, type ReactNode } from 'react'
import './AppErrorBoundary.css'

interface AppErrorBoundaryProps {
  children: ReactNode
}

interface AppErrorBoundaryState {
  failed: boolean
}

export class AppErrorBoundary extends Component<AppErrorBoundaryProps, AppErrorBoundaryState> {
  state: AppErrorBoundaryState = { failed: false }

  static getDerivedStateFromError(): AppErrorBoundaryState {
    return { failed: true }
  }

  componentDidCatch(_error: Error, _info: ErrorInfo) {
    // Keep the user-facing fallback independent from internal error details.
  }

  render() {
    if (this.state.failed) {
      return (
        <main className="app-error-fallback" role="alert">
          <h1>TurbineIQ could not display this screen</h1>
          <p>Reload the workspace to try again.</p>
          <button type="button" onClick={() => window.location.reload()}>Reload workspace</button>
        </main>
      )
    }

    return this.props.children
  }
}
