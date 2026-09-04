import { Activity, Eye, EyeOff, LayoutDashboard, LogOut, Menu, Search, ShieldCheck, Users, X } from "lucide-react";
import { useState, type ReactNode } from "react";
import { NavLink } from "react-router-dom";
import { useAuth } from "../../features/auth/AuthProvider";
import { usePatientContext } from "../../features/patients/PatientContext";

export function AppShell({ children }: { children: ReactNode }) {
  const [menuOpen, setMenuOpen] = useState(false);
  const { user, logout } = useAuth();
  const { privacyMask, setPrivacyMask } = usePatientContext();
  return (
    <div className="app-shell">
      <a className="skip-link" href="#main-content">Zum Inhalt springen</a>
      <aside className={`sidebar ${menuOpen ? "sidebar-open" : ""}`} aria-label="Hauptnavigation">
        <div className="brand"><span className="brand-mark"><Activity aria-hidden="true" /></span><span><strong>CareSignal</strong><small>FHIR Monitoring</small></span></div>
        <nav>
          <NavLink to="/" end onClick={() => setMenuOpen(false)}><LayoutDashboard aria-hidden="true" />Übersicht</NavLink>
          <NavLink to="/patients" onClick={() => setMenuOpen(false)}><Users aria-hidden="true" />Patienten</NavLink>
          <NavLink to="/patient" onClick={() => setMenuOpen(false)}><Activity aria-hidden="true" />Patientenakte</NavLink>
        </nav>
        <div className="sidebar-security"><ShieldCheck aria-hidden="true" /><span><strong>Geschützte Sitzung</strong><small>FHIR-Daten werden nicht lokal gespeichert.</small></span></div>
      </aside>
      {menuOpen ? <button className="scrim" aria-label="Navigation schließen" onClick={() => setMenuOpen(false)} /> : null}
      <div className="app-column">
        <header className="topbar">
          <button className="icon-button menu-button" aria-label={menuOpen ? "Navigation schließen" : "Navigation öffnen"} onClick={() => setMenuOpen(!menuOpen)}>{menuOpen ? <X /> : <Menu />}</button>
          <div className="topbar-context"><span className="system-status"><i aria-hidden="true" />System verbunden</span><span className="desktop-only">Klinischer Arbeitsbereich</span></div>
          <div className="topbar-actions">
            <NavLink className="icon-button" to="/patients" aria-label="Patienten suchen"><Search /></NavLink>
            <button className="icon-button" aria-pressed={privacyMask} aria-label={privacyMask ? "Datenschutzmaske ausschalten" : "Datenschutzmaske einschalten"} onClick={() => setPrivacyMask(!privacyMask)}>{privacyMask ? <EyeOff /> : <Eye />}</button>
            <div className="user-chip"><span aria-hidden="true">{user.displayName.slice(0, 1).toUpperCase()}</span><div><strong>{user.displayName}</strong><small>Angemeldet</small></div></div>
            <button className="icon-button" aria-label="Abmelden" onClick={() => void logout()}><LogOut /></button>
          </div>
        </header>
        <main id="main-content" className="main-content">{children}</main>
      </div>
    </div>
  );
}
