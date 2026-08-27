import { Component, type ErrorInfo, type ReactNode } from "react";

export class ErrorBoundary extends Component<{ children: ReactNode }, { error: Error | null }> {
  state = { error: null as Error | null };
  static getDerivedStateFromError(error: Error) { return { error }; }
  componentDidCatch(error: Error, info: ErrorInfo) { console.error("terminal render failure", error, info); }
  render() {
    if (this.state.error) return <main className="startup-error"><h1>界面启动失败</h1><p>{this.state.error.message}</p><small>请保留此窗口并将错误内容发送给开发者。</small></main>;
    return this.props.children;
  }
}
