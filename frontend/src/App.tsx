import { useState } from "react";
import { Outlet } from "react-router-dom";
import Sidebar from "./components/Sidebar";

export default function App() {
  const [collapsed, setCollapsed] = useState(false);
  return (
    <div className={`shell ${collapsed ? "collapsed" : ""}`}>
      <Sidebar collapsed={collapsed} toggle={() => setCollapsed(!collapsed)} />
      <main className="main">
        <Outlet />
      </main>
    </div>
  );
}
