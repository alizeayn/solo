/**
 * Keeps one broken tile from taking the workspace with it.
 *
 * Dockview renders every panel into the same React tree. Without a boundary, an
 * error thrown while rendering *any* panel unmounts the whole workspace: the
 * shell stays visible but every tile goes blank, which reads as "everything
 * stopped working" and gives no clue which tile was at fault.
 *
 * This boundary contains the damage and names the panel, so a failure is
 * diagnosable from the screen rather than only from the console.
 */

import { Component, type ErrorInfo, type ReactNode } from 'react'

interface Props {
  /** Shown in the message, so the failing tile is identifiable. */
  name: string
  children: ReactNode
}

interface State {
  error: Error | null
}

export default class PanelErrorBoundary extends Component<Props, State> {
  state: State = { error: null }

  static getDerivedStateFromError(error: Error): State {
    return { error }
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    // Kept: the console is where the stack belongs, the UI is where the
    // summary belongs.
    console.error(`panel "${this.props.name}" failed to render`, error, info)
  }

  private reset = () => this.setState({ error: null })

  render(): ReactNode {
    const { error } = this.state
    if (!error) return this.props.children

    return (
      <div className="panel panel--error" role="alert">
        <div className="panel__bar">
          <span className="panel__bar-title">{this.props.name}</span>
          <span className="header__spacer" />
          <span className="pill pill--danger">failed</span>
        </div>
        <div className="panel__body">
          <div className="empty">
            <div className="empty__glyph">!</div>
            <div className="empty__title">This tile stopped working</div>
            <div className="empty__text">
              The rest of the workspace is unaffected — this panel failed on its
              own. The reason is below and in the browser console.
            </div>
            <pre className="panel__error-detail">{error.message}</pre>
            <button type="button" className="btn btn--sm" onClick={this.reset}>
              Try again
            </button>
          </div>
        </div>
      </div>
    )
  }
}
