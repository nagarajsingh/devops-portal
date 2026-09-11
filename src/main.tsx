import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
import "./styles.css";
import "./feature.css";
import "./notifications.css";
import "./deployment-management.css";
import "./deployment-management-refinements.css";
import "./features/monitoring/monitoring.css";
import "./features/monitoring/categories.css";
import "./features/monitoring/details.css";
import "./features/monitoring/orange-premium.css";
import "./features/monitoring/table-pagination.css";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);
