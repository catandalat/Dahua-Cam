import { useEffect, useState } from "react";
import { NavLink, Route, Routes, useLocation } from "react-router-dom";
import AlertBanner from "./components/AlertBanner";
import LivePage from "./pages/LivePage";
import InsidePage from "./pages/InsidePage";
import HistoryPage from "./pages/HistoryPage";
import StatsPage from "./pages/StatsPage";
import ViolationsPage from "./pages/ViolationsPage";
import CamerasPage from "./pages/CamerasPage";
import PlatesPage from "./pages/PlatesPage";
import FlowPage from "./pages/FlowPage";
import RegistryPage from "./pages/RegistryPage";
import WatchPage from "./pages/WatchPage";
import MonitorPage from "./pages/MonitorPage";
import MapPage from "./pages/MapPage";

const links = [
  { to: "/", label: "Trực tiếp" },
  { to: "/map", label: "Bản đồ" },
  { to: "/inside", label: "Trong khu vực" },
  { to: "/history", label: "Lịch sử" },
  { to: "/stats", label: "Thống kê" },
  { to: "/flow", label: "Lưu lượng" },
  { to: "/violations", label: "Vi phạm" },
  { to: "/cameras", label: "Camera" },
  { to: "/plates", label: "Danh sách biển" },
  { to: "/registry", label: "Đăng ký xe" },
];

export default function App() {
  const [menuOpen, setMenuOpen] = useState(false);
  const location = useLocation();

  useEffect(() => {
    setMenuOpen(false);
  }, [location.pathname]);

  useEffect(() => {
    document.body.style.overflow = menuOpen ? "hidden" : "";
    return () => {
      document.body.style.overflow = "";
    };
  }, [menuOpen]);

  const nav = (
    <nav className="flex flex-col gap-1">
      <AlertBanner onNavigate={() => setMenuOpen(false)} />
      {links.map((l) => (
        <NavLink
          key={l.to}
          to={l.to}
          end={l.to === "/"}
          onClick={() => setMenuOpen(false)}
          className={({ isActive }) =>
            `rounded-lg px-3 py-2.5 text-sm transition ${
              isActive ? "bg-accent/15 text-accent" : "text-slate-300 hover:bg-white/5 active:bg-white/10"
            }`
          }
        >
          {l.label}
        </NavLink>
      ))}
    </nav>
  );

  return (
    <div className="min-h-screen flex flex-col md:flex-row">
      {/* Mobile top bar */}
      <header className="md:hidden sticky top-0 z-40 border-b border-line bg-panel/95 backdrop-blur px-3 py-2.5 flex items-center gap-3 safe-pb">
        <button
          type="button"
          aria-label="Mở menu"
          className="w-10 h-10 rounded-lg border border-line flex items-center justify-center text-lg"
          onClick={() => setMenuOpen(true)}
        >
          ☰
        </button>
        <div className="min-w-0 flex-1">
          <div className="text-[10px] uppercase tracking-[0.18em] text-slate-500">ANPR · ITC413</div>
          <div className="font-semibold text-sm truncate">Quản trị vận hành</div>
        </div>
        <NavLink
          to="/watch"
          className="text-xs border border-danger/40 text-danger rounded-lg px-2.5 py-1.5 shrink-0"
        >
          Truy vết biển số
        </NavLink>
      </header>

      {/* Mobile drawer overlay */}
      {menuOpen && (
        <button
          type="button"
          aria-label="Đóng menu"
          className="md:hidden fixed inset-0 z-40 bg-black/60"
          onClick={() => setMenuOpen(false)}
        />
      )}

      <aside
        className={`
          fixed md:static inset-y-0 left-0 z-50 w-[min(18rem,88vw)]
          border-r border-line bg-panel backdrop-blur
          px-4 py-5 flex flex-col gap-5
          transition-transform duration-200 ease-out
          ${menuOpen ? "translate-x-0" : "-translate-x-full md:translate-x-0"}
        `}
      >
        <div className="flex items-start justify-between gap-2">
          <div>
            <div className="text-xs uppercase tracking-[0.2em] text-slate-500">Dahua ITC413</div>
            <h1 className="text-lg font-semibold mt-1">Quản trị ANPR</h1>
          </div>
          <button
            type="button"
            className="md:hidden w-9 h-9 rounded-lg border border-line text-slate-400"
            aria-label="Đóng"
            onClick={() => setMenuOpen(false)}
          >
            ✕
          </button>
        </div>
        {nav}
        <div className="mt-auto text-xs text-slate-500">Đa cổng · thu nhận & vận hành</div>
      </aside>

      <main className="flex-1 p-3 sm:p-4 md:p-6 overflow-auto w-full min-w-0">
        <Routes>
          <Route path="/" element={<LivePage />} />
          <Route path="/map" element={<MapPage />} />
          <Route path="/monitor" element={<MonitorPage />} />
          <Route path="/inside" element={<InsidePage />} />
          <Route path="/history" element={<HistoryPage />} />
          <Route path="/stats" element={<StatsPage />} />
          <Route path="/flow" element={<FlowPage />} />
          <Route path="/violations" element={<ViolationsPage />} />
          <Route path="/cameras" element={<CamerasPage />} />
          <Route path="/plates" element={<PlatesPage />} />
          <Route path="/registry" element={<RegistryPage />} />
          <Route path="/watch" element={<WatchPage />} />
        </Routes>
      </main>
    </div>
  );
}
