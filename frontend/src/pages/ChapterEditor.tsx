import { useEffect, useState } from "react";
import { useParams, Link } from "react-router-dom";
import { api } from "../lib/api";

interface ChapterData {
  id: string;
  index: number;
  title: string;
  content: string | null;
  summary: string | null;
  outline: Record<string, unknown> | null;
  target_word_count: number;
  actual_word_count: number;
  status: string;
}

function isUUID(s: string): boolean {
  return /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(s);
}

export default function ChapterEditor() {
  const { id, ch } = useParams<{ id: string; ch: string }>();
  const chParam = ch || "1";
  const chapterIndex = isUUID(chParam) ? null : parseInt(chParam, 10);
  const chapterId = isUUID(chParam) ? chParam : null;
  const [chapter, setChapter] = useState<ChapterData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [tab, setTab] = useState<"content" | "outline">("content");

  useEffect(() => {
    if (!id) return;
    setLoading(true);
    const promise = chapterId
      ? api.chapters.get(chapterId)
      : api.chapters.getByIndex(id, chapterIndex || 1);
    promise
      .then(setChapter)
      .catch((e) => setError(e.message || "加载失败"))
      .finally(() => setLoading(false));
  }, [id, chapterId, chapterIndex]);

  if (loading) {
    return (
      <div className="max-w-4xl mx-auto p-6 text-center text-slate-400 mt-20">
        正在加载章节...
      </div>
    );
  }

  if (error || !chapter) {
    return (
      <div className="max-w-4xl mx-auto p-6">
        <Link
          to={`/project/${id}/write`}
          className="text-sm text-indigo-400 hover:text-indigo-300 mb-4 inline-block"
        >
          ← 返回写作台
        </Link>
        <div className="bg-slate-800 border border-slate-700 rounded-lg p-6 text-center">
          <p className="text-slate-400">{error || "章节未找到"}</p>
        </div>
      </div>
    );
  }

  return (
    <div className="max-w-4xl mx-auto p-6">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <Link
            to={`/project/${id}/write`}
            className="text-sm text-indigo-400 hover:text-indigo-300 mb-2 inline-block"
          >
            ← 返回写作台
          </Link>
          <h2 className="text-xl font-medium">
            第{chapter.index}章 {chapter.title}
          </h2>
        </div>
        <div className="flex items-center gap-3 text-xs text-slate-400">
          <span>
            字数：{chapter.actual_word_count} / {chapter.target_word_count} 目标
          </span>
          <ChapterStatusBadge status={chapter.status} />
        </div>
      </div>

      {/* Chapter summary */}
      {chapter.summary && (
        <div className="bg-slate-800 border border-slate-700 rounded-lg p-4 mb-4">
          <h3 className="text-xs font-medium text-indigo-400 mb-2">本章摘要</h3>
          <p className="text-sm text-slate-300">{chapter.summary}</p>
        </div>
      )}

      {/* Tabs */}
      <div className="flex gap-2 mb-4 border-b border-slate-700 pb-2">
        <button
          onClick={() => setTab("content")}
          className={`px-3 py-1 text-sm rounded ${
            tab === "content"
              ? "bg-indigo-600 text-white"
              : "bg-slate-800 text-slate-400 hover:text-slate-200"
          }`}
        >
          正文
        </button>
        <button
          onClick={() => setTab("outline")}
          className={`px-3 py-1 text-sm rounded ${
            tab === "outline"
              ? "bg-indigo-600 text-white"
              : "bg-slate-800 text-slate-400 hover:text-slate-200"
          }`}
        >
          章节大纲
        </button>
      </div>

      {/* Content tab */}
      {tab === "content" && (
        <div className="bg-slate-800 border border-slate-700 rounded-lg p-6 min-h-[60vh]">
          {chapter.content ? (
            <div className="text-sm text-slate-300 leading-relaxed whitespace-pre-wrap font-sans">
              {chapter.content}
            </div>
          ) : (
            <div className="text-center mt-20">
              <p className="text-slate-500 mb-4">本章尚未生成正文内容。</p>
              <Link
                to={`/project/${id}/write`}
                className="text-sm bg-indigo-600 hover:bg-indigo-500 text-white rounded px-4 py-2"
              >
                前往写作台生成
              </Link>
            </div>
          )}
        </div>
      )}

      {/* Outline tab */}
      {tab === "outline" && (
        <div className="bg-slate-800 border border-slate-700 rounded-lg p-6 min-h-[40vh]">
          {chapter.outline ? (
            <OutlineView outline={chapter.outline} />
          ) : (
            <p className="text-sm text-slate-500 text-center mt-12">暂无大纲。</p>
          )}
        </div>
      )}
    </div>
  );
}

function OutlineView({ outline }: { outline: Record<string, any> }) {
  const scenes = outline.scenes;

  return (
    <div className="space-y-4">
      {outline.summary && typeof outline.summary === "string" && (
        <div className="bg-slate-700/50 rounded p-3 mb-4">
          <span className="text-xs text-slate-400">概要：</span>
          <span className="text-sm text-slate-300">{outline.summary}</span>
        </div>
      )}

      {scenes && Array.isArray(scenes) && scenes.length > 0 ? (
        <div>
          <h4 className="text-xs font-medium text-slate-400 mb-3">场景节拍</h4>
          {scenes.map((s: any, i: number) => (
            <div key={i} className="bg-slate-700/30 border border-slate-700 rounded-lg p-3 mb-2">
              <div className="flex items-center gap-2 mb-2">
                <span className="text-xs bg-indigo-600 text-white px-2 py-0.5 rounded">
                  节拍 {s.beat || s.scene || i + 1}
                </span>
                {s.purpose && (
                  <span className="text-xs text-slate-400">{s.purpose}</span>
                )}
              </div>
              {s.description && (
                <p className="text-sm text-slate-300 mb-2">{s.description}</p>
              )}
              <div className="flex flex-wrap gap-2 text-[10px]">
                {s.characters_involved && Array.isArray(s.characters_involved) && (
                  <span className="bg-slate-700 px-2 py-0.5 rounded text-slate-400">
                    登场：{s.characters_involved.join("、")}
                  </span>
                )}
                {s.characters && Array.isArray(s.characters) && (
                  <span className="bg-slate-700 px-2 py-0.5 rounded text-slate-400">
                    角色：{s.characters.map((c: any) => c.name || c).join("、")}
                  </span>
                )}
                {s.emotion_curve && (
                  <span className="bg-slate-700 px-2 py-0.5 rounded text-slate-400">
                    情绪：{s.emotion_curve}
                  </span>
                )}
                {s.hook_planted && (
                  <span className="bg-emerald-700/50 px-2 py-0.5 rounded text-emerald-300">
                    伏笔：{s.hook_planted}
                  </span>
                )}
                {s.hook_plant && (
                  <span className="bg-emerald-700/50 px-2 py-0.5 rounded text-emerald-300">
                    伏笔：{s.hook_plant}
                  </span>
                )}
                {s.hook_resolved && (
                  <span className="bg-amber-700/50 px-2 py-0.5 rounded text-amber-300">
                    回收：{s.hook_resolved}
                  </span>
                )}
              </div>
            </div>
          ))}
        </div>
      ) : (
        <div>
          <pre className="text-sm text-slate-400 whitespace-pre-wrap font-mono">
            {JSON.stringify(outline, null, 2)}
          </pre>
        </div>
      )}
    </div>
  );
}

function ChapterStatusBadge({ status }: { status: string }) {
  const colors: Record<string, string> = {
    draft: "bg-slate-600 text-slate-300",
    outlining: "bg-slate-600 text-slate-300",
    outlined: "bg-blue-600 text-blue-100",
    writing: "bg-amber-600 text-amber-100",
    reviewing: "bg-purple-600 text-purple-100",
    completed: "bg-emerald-600 text-emerald-100",
  };
  const labels: Record<string, string> = {
    draft: "草稿",
    outlining: "大纲中",
    outlined: "已定纲",
    writing: "写作中",
    reviewing: "审核中",
    completed: "已完成",
  };
  return (
    <span className={`px-2 py-0.5 rounded text-[10px] ${colors[status] || "bg-slate-600"}`}>
      {labels[status] || status}
    </span>
  );
}
