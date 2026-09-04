import { createRoot } from "react-dom/client";
import { App } from "./app/App";
import { AppProviders } from "./app/providers/AppProviders";
import "./styles/index.css";

const root = document.getElementById("root");
if (!root) throw new Error("Anwendungscontainer fehlt.");
createRoot(root).render(<AppProviders><App /></AppProviders>);
