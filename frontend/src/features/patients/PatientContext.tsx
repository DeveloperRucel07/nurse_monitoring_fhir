import { createContext, useContext, useState, type ReactNode } from "react";

type PatientContextValue = {
  selectedPatientId: string | null;
  selectPatient: (id: string) => void;
  privacyMask: boolean;
  setPrivacyMask: (enabled: boolean) => void;
};

const PatientContext = createContext<PatientContextValue | null>(null);

export function PatientContextProvider({ children }: { children: ReactNode }) {
  const [selectedPatientId, setSelectedPatientId] = useState<string | null>(null);
  const [privacyMask, setPrivacyMask] = useState(false);
  return (
    <PatientContext.Provider value={{ selectedPatientId, selectPatient: setSelectedPatientId, privacyMask, setPrivacyMask }}>
      {children}
    </PatientContext.Provider>
  );
}

export function usePatientContext(): PatientContextValue {
  const value = useContext(PatientContext);
  if (!value) throw new Error("PatientContextProvider fehlt.");
  return value;
}
