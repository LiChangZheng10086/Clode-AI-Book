import { Outlet, useParams, Link, useLocation, useNavigate } from "react-router-dom";
import { useEffect, useState, useRef } from "react";
import { useProjectStore } from "../stores/projectStore";
import type { Novel } from "../stores/projectStore";
import { api } from "../lib/api";
import { BookOpen, ChevronDown, Plus } from "lucide-react";

export default function ProjectLayout() {
  const { id } = useParams<{ id: string }>();
  const location = useLocation();
  const navigate = useNavigate();
  const { currentNovel, setCurrentNovel, novels, setNovels } = useProjectStore();
  const [menuOpen, setMenuOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (id && (!currentNovel || currentNovel.id !== id)) {
      api.novels.get(id).then(setCurrentNovel).catch(console.error);
    }
  }, [id]);

  useEffect(() => {
    api.novels.list().then(setNovels).catch(console.error);
  }, []);

  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setMenuOpen(false);
      }
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, []);

  if (!currentNovel) return null;

  const navItems = [
    { path: `/project/${id}`, label: "总览" },
    { path: `/project/${id}/preprocess`, label: "预处理" },
    { path: `/project/${id}/outline`, label: "大纲" },
    { path: `/project/${id}/write`, label: "写作" },
    { path: `/project/${id}/hooks`, label: "钩子" },
    { path: `/project/${id}/settings`, label: "设定" },
  ];

  const switchNovel = (novel: Novel) => {
    setCurrentNovel(novel);
    setMenuOpen(false);
    navigate(`/project/${novel.id}`);
  };

  return (
    <div className="min-h-screen bg-slate-900">
      {/* Top nav */}
      <header className="border-b border-slate-700 bg-slate-800 px-4 py-2 flex items-center gap-4">
        {/* Project switcher */}
        <div className="relative" ref={menuRef}>
          <button
            onClick={() => setMenuOpen(!menuOpen)}
            className="flex items-center gap-2 text-slate-200 hover:text-white px-2 py-1 rounded hover:bg-slate-700"
          >
            <BookOpen size={16} />
            <span className="font-medium">{currentNovel.title}</span>
            <ChevronDown size={14} />
          </button>
          {menuOpen && (
            <div className="absolute top-full left-0 mt-1 w-64 bg-slate-800 border border-slate-700 rounded-lg shadow-xl z-50">
              {novels.map((n) => (
                <button
                  key={n.id}
                  onClick={() => switchNovel(n)}
                  className={`w-full text-left px-4 py-3 hover:bg-slate-700 flex items-center gap-3 ${
                    n.id === id ? "bg-slate-700" : ""
                  }`}
                >
                  <BookOpen size={14} />
                  <div>
                    <div className="text-sm">{n.title}</div>
                    <div className="text-xs text-slate-400">
                      {n.genre} · {n.status}
                    </div>
                  </div>
                </button>
              ))}
              <Link
                to="/"
                className="block px-4 py-2 text-sm text-slate-400 hover:text-slate-200 border-t border-slate-700 flex items-center gap-2"
              >
                <Plus size={14} /> 新建项目
              </Link>
            </div>
          )}
        </div>

        {/* Nav links */}
        <nav className="flex gap-1 ml-4">
          {navItems.map((item) => {
            const active = location.pathname === item.path ||
              (item.path !== `/project/${id}` && location.pathname.startsWith(item.path));
            return (
              <Link
                key={item.path}
                to={item.path}
                className={`px-3 py-1 text-sm rounded ${
                  active
                    ? "bg-indigo-600 text-white"
                    : "text-slate-400 hover:text-slate-200 hover:bg-slate-700"
                }`}
              >
                {item.label}
              </Link>
            );
          })}
        </nav>
      </header>

      {/* Page content */}
      <main>
        <Outlet />
      </main>
    </div>
  );
}
