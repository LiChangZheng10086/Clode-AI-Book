import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../lib/api";
import { useProjectStore } from "../stores/projectStore";
import { BookOpen, Plus, Trash2 } from "lucide-react";

export default function ProjectList() {
  const [title, setTitle] = useState("");
  const [genre, setGenre] = useState("");
  const [targetChapters, setTargetChapters] = useState(100);
  const [creating, setCreating] = useState(false);
  const { novels, setNovels } = useProjectStore();
  const navigate = useNavigate();

  useEffect(() => {
    api.novels.list().then(setNovels).catch(console.error);
  }, []);

  const createNovel = async () => {
    if (!title.trim()) return;
    setCreating(true);
    try {
      const novel = await api.novels.create({ title: title.trim(), genre: genre.trim(), target_chapters: targetChapters });
      navigate(`/project/${novel.id}/preprocess`);
    } finally {
      setCreating(false);
    }
  };

  const deleteNovel = async (id: string, title: string) => {
    if (!confirm(`确定要删除「${title}」吗？此操作不可恢复。`)) return;
    await api.novels.delete(id);
    setNovels(novels.filter((n) => n.id !== id));
  };

  return (
    <div className="min-h-screen bg-slate-900 flex flex-col items-center pt-24 px-4">
      <h1 className="text-3xl font-bold mb-10">Clode AI Book</h1>

      {/* Create new */}
      <div className="w-full max-w-lg bg-slate-800 border border-slate-700 rounded-xl p-6 mb-10">
        <h2 className="text-lg font-medium mb-4">创建新项目</h2>
        <div className="flex flex-col gap-3">
          <input
            type="text"
            placeholder="书名"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            className="bg-slate-700 border border-slate-600 rounded px-3 py-2 text-sm outline-none focus:border-indigo-500"
            onKeyDown={(e) => e.key === "Enter" && createNovel()}
          />
          <input
            type="text"
            placeholder="类型 (选填，如 仙侠/科幻/都市)"
            value={genre}
            onChange={(e) => setGenre(e.target.value)}
            className="bg-slate-700 border border-slate-600 rounded px-3 py-2 text-sm outline-none focus:border-indigo-500"
            onKeyDown={(e) => e.key === "Enter" && createNovel()}
          />
          <div className="flex items-center gap-2">
            <label className="text-sm text-slate-400 whitespace-nowrap">目标章节数</label>
            <input
              type="number"
              min={1}
              max={5000}
              value={targetChapters}
              onChange={(e) => setTargetChapters(Number(e.target.value))}
              className="bg-slate-700 border border-slate-600 rounded px-3 py-2 text-sm outline-none focus:border-indigo-500 w-24"
            />
          </div>
          <button
            onClick={createNovel}
            disabled={creating || !title.trim()}
            className="bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 disabled:cursor-not-allowed text-white rounded px-4 py-2 text-sm font-medium transition-colors flex items-center justify-center gap-2"
          >
            <Plus size={16} /> {creating ? "创建中..." : "创建并开始预处理"}
          </button>
        </div>
      </div>

      {/* Existing projects */}
      {novels.length > 0 ? (
        <div className="w-full max-w-lg">
          <h2 className="text-sm text-slate-400 mb-3">已有项目</h2>
          <div className="flex flex-col gap-2">
            {novels.map((novel) => (
              <div
                key={novel.id}
                className="flex items-center gap-3 bg-slate-800 border border-slate-700 rounded-lg p-4 hover:border-slate-600 transition-colors group"
              >
                <button
                  onClick={() => navigate(`/project/${novel.id}`)}
                  className="flex items-center gap-3 flex-1 text-left"
                >
                  <BookOpen size={18} className="text-indigo-400" />
                  <div>
                    <div className="font-medium text-sm">{novel.title}</div>
                    <div className="text-xs text-slate-400">
                      {novel.genre || "未分类"} · {novel.status} · {novel.target_chapters}章
                    </div>
                  </div>
                </button>
                <button
                  onClick={(e) => { e.stopPropagation(); deleteNovel(novel.id, novel.title); }}
                  className="text-slate-500 hover:text-red-400 hover:bg-red-400/10 rounded p-1.5 transition-colors"
                  title="删除项目"
                >
                  <Trash2 size={16} />
                </button>
              </div>
            ))}
          </div>
        </div>
      ) : (
        <div className="w-full max-w-lg text-center py-10">
          <BookOpen size={40} className="text-slate-600 mx-auto mb-3" />
          <p className="text-sm text-slate-500">还没有项目，在上方创建你的第一本 AI 小说</p>
        </div>
      )}
    </div>
  );
}
