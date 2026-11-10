import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter, Route, Routes } from "react-router-dom";
import App from "./App";
import Chat from "./pages/Chat";
import "./styles.css";

createRoot(document.getElementById("app")!).render(
  <StrictMode>
    <BrowserRouter>
      <Routes>
        <Route element={<App />}>
          <Route index element={<Chat />} />
          <Route path="c/:id" element={<Chat />} />
          <Route path="*" element={<Chat />} />
        </Route>
      </Routes>
    </BrowserRouter>
  </StrictMode>,
);
