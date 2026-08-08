import React from "react";
import ReactDOM from "react-dom/client";
import "vazirmatn/Vazirmatn-font-face.css";
import "./styles/global.css";
import App from "./App";
import { AppProvider } from "./state/AppContext";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <AppProvider>
      <App />
    </AppProvider>
  </React.StrictMode>,
);
