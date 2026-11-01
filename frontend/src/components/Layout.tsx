import { NavLink, Outlet } from "react-router-dom";
import { Shield, Zap, List } from "lucide-react";

export function Layout() {
  return (
    <div className="layout">
      <aside className="sidebar">
        <div className="sidebar__logo">
          <Shield size={22} color="var(--accent)" />
          <span>QueueGuard</span>
        </div>
        <nav className="sidebar__nav">
          <NavLink to="/" end className={({ isActive }) => isActive ? "nav-link nav-link--active" : "nav-link"}>
            <List size={16} /> Endpoints
          </NavLink>
          <NavLink to="/events" className={({ isActive }) => isActive ? "nav-link nav-link--active" : "nav-link"}>
            <Zap size={16} /> All Events
          </NavLink>
        </nav>
        <div className="sidebar__footer">
          <span className="text-muted">v0.1.0</span>
        </div>
      </aside>
      <main className="main-content">
        <Outlet />
      </main>

      <style>{`
        .layout { display: flex; min-height: 100vh; }
        .sidebar {
          width: 220px; flex-shrink: 0;
          background: var(--surface);
          border-right: 1px solid var(--border);
          display: flex; flex-direction: column;
          padding: 1.25rem 0;
        }
        .sidebar__logo {
          display: flex; align-items: center; gap: 0.5rem;
          padding: 0 1.25rem 1.5rem;
          font-weight: 600; font-size: 1rem;
          border-bottom: 1px solid var(--border);
        }
        .sidebar__nav {
          flex: 1; display: flex; flex-direction: column;
          padding: 1rem 0.75rem; gap: 0.25rem;
        }
        .nav-link {
          display: flex; align-items: center; gap: 0.5rem;
          padding: 0.5rem 0.75rem; border-radius: var(--radius);
          color: var(--text-muted); transition: all 0.15s;
        }
        .nav-link:hover { background: rgba(255,255,255,0.05); color: var(--text); text-decoration: none; }
        .nav-link--active { background: rgba(99,102,241,0.15); color: var(--accent); }
        .sidebar__footer { padding: 0 1.25rem 0.5rem; }
        .text-muted { color: var(--text-muted); font-size: 0.8rem; }
        .main-content { flex: 1; overflow: auto; padding: 2rem; }

        /* Global badge styles */
        .badge {
          display: inline-block; padding: 0.15rem 0.55rem;
          border-radius: 9999px; font-size: 0.75rem; font-weight: 500;
        }
        .badge--grey   { background: rgba(113,128,150,0.2); color: #718096; }
        .badge--blue   { background: rgba(99,102,241,0.2);  color: #818cf8; }
        .badge--green  { background: rgba(34,197,94,0.2);   color: #4ade80; }
        .badge--red    { background: rgba(239,68,68,0.2);   color: #f87171; }
        .badge--orange { background: rgba(245,158,11,0.2);  color: #fbbf24; }

        /* Cards */
        .card {
          background: var(--surface);
          border: 1px solid var(--border);
          border-radius: var(--radius);
          padding: 1.25rem;
        }

        /* Buttons */
        .btn {
          display: inline-flex; align-items: center; gap: 0.4rem;
          padding: 0.45rem 1rem; border-radius: var(--radius);
          font-weight: 500; transition: all 0.15s;
        }
        .btn-primary { background: var(--accent); color: #fff; }
        .btn-primary:hover { background: var(--accent-hover); }
        .btn-ghost {
          background: transparent; border: 1px solid var(--border);
          color: var(--text);
        }
        .btn-ghost:hover { background: rgba(255,255,255,0.05); }
        .btn-danger { background: rgba(239,68,68,0.15); color: #f87171; border: 1px solid rgba(239,68,68,0.3); }
        .btn-danger:hover { background: rgba(239,68,68,0.25); }
        .btn:disabled { opacity: 0.5; cursor: not-allowed; }

        /* Page header */
        .page-header {
          display: flex; align-items: center; justify-content: space-between;
          margin-bottom: 1.5rem;
        }
        .page-title { font-size: 1.25rem; font-weight: 600; }

        /* Table */
        .table-wrap { overflow-x: auto; }
        table { width: 100%; border-collapse: collapse; }
        th, td { text-align: left; padding: 0.65rem 1rem; border-bottom: 1px solid var(--border); }
        th { color: var(--text-muted); font-weight: 500; font-size: 0.8rem; text-transform: uppercase; letter-spacing: 0.05em; }
        tr:last-child td { border-bottom: none; }
        tr:hover td { background: rgba(255,255,255,0.02); }

        /* Empty state */
        .empty { padding: 3rem; text-align: center; color: var(--text-muted); }

        /* Error */
        .error-box {
          background: rgba(239,68,68,0.1); border: 1px solid rgba(239,68,68,0.3);
          border-radius: var(--radius); padding: 1rem; color: #f87171;
        }
      `}</style>
    </div>
  );
}
