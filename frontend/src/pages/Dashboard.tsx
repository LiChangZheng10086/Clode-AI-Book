import { useParams, Link } from "react-router-dom";
import { useEffect, useState } from "react";
import { useProjectStore } from "../stores/projectStore";
import { api } from "../lib/api";
import { useNavigate } from "react-router-dom";
import { Edit3, AlertTriangle, BookOpen, ArrowRight, Trash2 } from "lucide-react";

const STATUS_LABELS: Record<string, string> = {
  draft: "草稿",
  preprocess: "预处理中",
  writing: "写作中",
  completed: "已完成",
  archived: "已归档",
};

export default function Dashboard() {
  const { id } = useParams<{ id: string }>();
  const { currentNovel } = useProjectStore();
  const [hookCount, setHookCount] = useState<number | null>(null);
  const [deleting, setDeleting] = useState(false);
  const navigate = useNavigate();

  useEffect(() => {
    if (id) {
      api.hooks.list(id).then(hooks => setHookCount(hooks.length)).catch(() => setHookCount(null));
    }
  }, [id]);

  if (!currentNovel || !id) return null;

  const handleDelete = async () => {
    if (!confirm(`确定要删除「${currentNovel.title}」及其所有章节、角色、钩子数据吗？此操作不可恢复。`)) return;
    setDeleting(true);
    try {
      await api.novels.delete(id);
      navigate("/", { replace: true });
    } catch (e: any) {
      alert(`删除失败: ${e.message}`);
      setDeleting(false);
    }
  };

  const progress = currentNovel.current_chapter_index
    ? Math.round((currentNovel.current_chapter_index / currentNovel.target_chapters) * 100)
    : 0;

  const cards = [
    {
      title: "进度",
      value: currentNovel.current_chapter_index
        ? `已写 ${currentNovel.current_chapter_index} 章`
        : "尚未开始",
      sub: `目标 ${currentNovel.target_chapters} 章`,
      progress,
    },
    {
      title: "钩子状态",
      value: hookCount === null ? "加载中..." : hookCount === 0 ? "暂无钩子" : `共 ${hookCount} 个`,
      sub: currentNovel.status === "draft" ? "请先运行预处理" : "",
    },
    { title: "状态", value: STATUS_LABELS[currentNovel.status] || currentNovel.status, sub: "" },
  ];

  return (
    <div className="max-w-4xl mx-auto p-6">
      {/* Stat cards */}
      <div className="grid grid-cols-3 gap-4 mb-8">
        {cards.map((card) => (
          <div key={card.title} className="bg-slate-800 border border-slate-700 rounded-lg p-4">
            <div className="text-xs text-slate-400 mb-1">{card.title}</div>
            <div className="text-lg font-medium">{card.value}</div>
            {card.sub && <div className="text-xs text-slate-500 mt-1">{card.sub}</div>}
            {card.progress !== undefined && (
              <div className="mt-2 h-1.5 bg-slate-700 rounded-full overflow-hidden">
                <div
                  className="h-full bg-indigo-500 rounded-full transition-all"
                  style={{ width: `${card.progress}%` }}
                />
              </div>
            )}
          </div>
        ))}
      </div>

      {/* Quick actions */}
      <div className="bg-slate-800 border border-slate-700 rounded-lg p-6">
        <h2 className="font-medium mb-4">快速入口</h2>
        <div className="flex flex-col gap-2">
          {currentNovel.status === "draft" && (
            <QuickLink
              to={`/project/${id}/preprocess`}
              icon={<BookOpen size={16} />}
              label="开始预处理"
              desc="运行世界观、角色、风格、大纲 Agent"
            />
          )}
          {currentNovel.status === "preprocess" && (
            <QuickLink
              to={`/project/${id}/preprocess`}
              icon={<ArrowRight size={16} />}
              label="继续预处理"
              desc="继续未完成的预处理流程"
            />
          )}
          {currentNovel.status === "writing" && (
            <QuickLink
              to={`/project/${id}/write`}
              icon={<Edit3 size={16} />}
              label="继续写作"
              desc={`进入第 ${currentNovel.current_chapter_index || "?"} 章写作台`}
            />
          )}
          <QuickLink
            to={`/project/${id}/outline`}
            icon={<BookOpen size={16} />}
            label="查看大纲"
            desc="浏览和编辑全书大纲"
          />
          <QuickLink
            to={`/project/${id}/hooks`}
            icon={<AlertTriangle size={16} />}
            label="查看钩子"
            desc="管理伏笔的种植和回收"
          />
        </div>
      </div>

      {/* Danger zone */}
      <div className="mt-8 bg-red-950/20 border border-red-800/50 rounded-lg p-6">
        <h2 className="font-medium text-red-300 mb-2">危险操作</h2>
        <p className="text-xs text-slate-400 mb-4">
          删除项目将同时删除所有章节、角色、钩子、世界观设定等数据，此操作不可恢复。
        </p>
        <button
          onClick={handleDelete}
          disabled={deleting}
          className="bg-red-600 hover:bg-red-500 disabled:opacity-50 text-white rounded px-4 py-2 text-sm flex items-center gap-2"
        >
          <Trash2 size={14} />
          {deleting ? "删除中..." : "删除此项目"}
        </button>
      </div>
    </div>
  );
}

function QuickLink({
  to,
  icon,
  label,
  desc,
}: {
  to: string;
  icon: React.ReactNode;
  label: string;
  desc: string;
}) {
  return (
    <Link
      to={to}
      className="flex items-center gap-3 bg-slate-700/50 hover:bg-slate-700 rounded-lg p-3 transition-colors group"
    >
      <span className="text-indigo-400">{icon}</span>
      <div className="flex-1">
        <div className="text-sm font-medium">{label}</div>
        <div className="text-xs text-slate-400">{desc}</div>
      </div>
      <ArrowRight size={14} className="text-slate-500 group-hover:text-slate-300" />
    </Link>
  );
}
