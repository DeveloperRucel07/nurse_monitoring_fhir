import { Component, type ReactNode } from "react";
import { FullPageState } from "../shared/components/States";

export class ErrorBoundary extends Component<{ children: ReactNode }, { failed: boolean }> {
  state = { failed: false };

  static getDerivedStateFromError(): { failed: boolean } {
    return { failed: true };
  }

  componentDidCatch(): void {
    // Absichtlich kein Browser-Logging: Fehlobjekte können Gesundheitsdaten enthalten.
  }

  render() {
    if (this.state.failed) return <FullPageState title="Darstellung nicht möglich" message="Die Ansicht wurde aus Sicherheitsgründen beendet. Laden Sie die Anwendung neu." />;
    return this.props.children;
  }
}
