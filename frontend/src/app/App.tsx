import { lazy, Suspense } from "react";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { PatientContextProvider } from "../features/patients/PatientContext";
import { LoadingState } from "../shared/components/States";
import { ErrorBoundary } from "./ErrorBoundary";
import { AppShell } from "./layout/AppShell";

const DashboardPage = lazy(() => import("../pages/DashboardPage").then((module) => ({ default: module.DashboardPage })));
const PatientsPage = lazy(() => import("../pages/PatientsPage").then((module) => ({ default: module.PatientsPage })));
const PatientDetailPage = lazy(() => import("../pages/PatientDetailPage").then((module) => ({ default: module.PatientDetailPage })));

export function App() {
  return <ErrorBoundary><BrowserRouter><PatientContextProvider><AppShell><Suspense fallback={<LoadingState />}><Routes>
    <Route path="/" element={<DashboardPage />} />
    <Route path="/patients" element={<PatientsPage />} />
    <Route path="/patient" element={<PatientDetailPage />} />
    <Route path="*" element={<Navigate to="/" replace />} />
  </Routes></Suspense></AppShell></PatientContextProvider></BrowserRouter></ErrorBoundary>;
}
