import { useEffect, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { api } from "../lib/api";

interface VolumeItem {
  id: string;
  index: number;
  title: string;
  summary: string | null;
  status: string;
}

interface ChapterItem {
  id: string;
  volume_id: string;
  index: number;
  title: string;
  outline: Record<string, unknown> | null;
  target_word_count: number;
  actual_word_count: number;
  status: string;
}

export default function Outline() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [volumes, setVolumes] = useState<VolumeItem[]>([]);
  const [chapters, setChapters] = useState<ChapterItem[]>([]);
  const [selectedVol, setSelectedVol] = useState<string | null>(null);
  const [selectedChapter, setSelectedChapter] = useState<ChapterItem | null>(null);

  useEffect(() => {
    if (id) api.chapters.listVolumes(id).then(setVolumes).catch(console.error);
  }, [id]);

  useEffect(() => {
    if (selectedVol) {
      api.chapters.list(selectedVol).then(setChapters).catch(console.error);
    } else {
      setChapters([]);
    }
  }, [selectedVol]);

  const handleVolClick = (volId: string) => {
    setSelectedVol(volId === selectedVol ? null : volId);
    setSelectedChapter(null);
  };

  const totalChapters = volumes.reduce((sum, v) => {
    // We don't have chapter count per volume from the list endpoint,
    // but we can approximate from chapter indices
    return sum;
  }, 0);

  return (
    <div className="flex h-[calc(100vh-48px)]">
      {/* ── Sidebar: Volumes + Chapters ── */}
      <div className="w-80 border-r border-slate-700 bg-slate-800 flex flex-col">
        <div className="p-4 border-b border-slate-700">
          <h3 className="text-sm font-medium text-slate-400">
            全书大纲
            {volumes.length > 0 && (
              <span className="ml-2 text-xs text-slate-500">
                {volumes.length} 卷
              </span>
            )}
          </h3>
        </div>

        <div className="flex-1 overflow-y-auto p-2">
          {volumes.length === 0 && (
            <p className="text-sm text-slate-500 p-4">暂无大纲数据，请先在预处理中生成大纲。</p>
          )}

          {volumes.map((vol) => (
            <div key={vol.id} className="mb-1">
              <button
                onClick={() => handleVolClick(vol.id)}
                className={`w-full text-left px-3 py-2 rounded text-sm flex items-center gap-2
                  ${selectedVol === vol.id
                    ? "bg-indigo-600/20 text-indigo-300 border border-indigo-500/30"
                    : "text-slate-300 hover:bg-slate-700/50 border border-transparent"
                  }`}
              >
                <span className="text-xs text-slate-500 w-8 shrink-0">
                  {selectedVol === vol.id ? "▼" : "▶"} 卷{vol.index}
                </span>
                <span className="truncate">{vol.title || `第${vol.index}卷`}</span>
              </button>

              {/* Chapters under this volume */}
              {selectedVol === vol.id && (
                <div className="ml-6 mt-1 space-y-0.5">
                  {chapters.length === 0 && (
                    <p className="text-xs text-slate-500 py-2 px-2">暂无章节</p>
                  )}
                  {chapters.map((ch) => (
                    <button
                      key={ch.id}
                      onClick={() => setSelectedChapter(ch)}
                      className={`w-full text-left px-3 py-1.5 rounded text-xs
                        ${selectedChapter?.id === ch.id
                          ? "bg-indigo-600/30 text-indigo-200"
                          : "text-slate-400 hover:bg-slate-700/50 hover:text-slate-300"
                        }`}
                    >
                      <span className="text-slate-500 mr-1.5">第{ch.index}章</span>
                      <span className="truncate">{ch.title}</span>
                      {ch.status === "outlining" && (
                        <span className="ml-1.5 text-[10px] bg-slate-600 px-1 rounded">大纲</span>
                      )}
                      {ch.status === "completed" && (
                        <span className="ml-1.5 text-[10px] bg-emerald-600/50 text-emerald-300 px-1 rounded">已成文</span>
                      )}
                    </button>
                  ))}
                </div>
              )}
            </div>
          ))}
        </div>
      </div>

      {/* ── Main: Chapter detail ── */}
      <div className="flex-1 overflow-y-auto p-6">
        {selectedChapter ? (
          <ChapterDetail chapter={selectedChapter} />
        ) : (
          <div className="text-center text-slate-500 mt-20">
            {volumes.length > 0
              ? "选择左侧章节查看详情"
              : "运行预处理生成大纲后，可在此查看全书结构"}
          </div>
        )}
      </div>
    </div>
  );
}

/* ── Chapter detail view ── */

function ChapterDetail({ chapter }: { chapter: ChapterItem }) {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const outline = chapter.outline as Record<string, any> | null;
  const scenes = outline?.scenes;

  return (
    <div className="max-w-2xl">
      <div className="mb-6">
        <h2 className="text-xl font-medium">
          第{chapter.index}章 {chapter.title}
        </h2>
        <div className="flex gap-4 mt-2 text-xs text-slate-400 items-center">
          <span>目标 {chapter.target_word_count} 字</span>
          <span>实际 {chapter.actual_word_count} 字</span>
          <ChapterStatusBadge status={chapter.status} />
          <button
            onClick={() => navigate(`/project/${id}/write/${chapter.id}`)}
            className="ml-auto text-xs bg-indigo-600 hover:bg-indigo-500 text-white rounded px-3 py-1"
          >
            查看正文 →
          </button>
        </div>
      </div>

      {/* Chapter summary (lean format from A4) */}
      {outline?.summary && typeof outline.summary === "string" && (
        <div className="bg-slate-800 border border-slate-700 rounded-lg p-4 mb-4">
          <h3 className="text-xs font-medium text-indigo-400 mb-2">本章概要</h3>
          <p className="text-sm text-slate-300">{outline.summary}</p>
        </div>
      )}

      {/* Scenes / beats (detailed format from A5) */}
      {scenes && Array.isArray(scenes) && scenes.length > 0 ? (
        <div className="space-y-4">
          <h3 className="text-sm font-medium text-slate-400">场景节拍</h3>
          {scenes.map((s: any, i: number) => (
            <div key={i} className="bg-slate-800 border border-slate-700 rounded-lg p-4">
              <div className="flex items-center gap-2 mb-2">
                <span className="text-xs bg-indigo-600 text-white px-2 py-0.5 rounded">
                  节拍 {s.beat || s.scene || i + 1}
                </span>
                {s.purpose && (
                  <span className="text-xs text-slate-400">{s.purpose}</span>
                )}
              </div>
              {s.description && (
                <p className="text-sm text-slate-300">{s.description}</p>
              )}
              <div className="flex flex-wrap gap-2 mt-3 text-[10px]">
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
                {s.hook_advanced && Array.isArray(s.hook_advanced) && (
                  <span className="bg-amber-700/50 px-2 py-0.5 rounded text-amber-300">
                    推进钩子：{s.hook_advanced.join(", ")}
                  </span>
                )}
                {s.information_revealed && (
                  <span className="bg-slate-700 px-2 py-0.5 rounded text-slate-400">
                    揭示：{s.information_revealed}
                  </span>
                )}
              </div>
            </div>
          ))}
        </div>
      ) : outline && !outline.summary ? (
        <div className="bg-slate-800 border border-slate-700 rounded-lg p-4">
          <pre className="text-sm text-slate-400 whitespace-pre-wrap font-mono">
            {JSON.stringify(outline, null, 2)}
          </pre>
        </div>
      ) : null}

      {!outline && (
        <p className="text-sm text-slate-500">暂无章节大纲详情。</p>
      )}
    </div>
  );
}

function ChapterStatusBadge({ status }: { status: string }) {
  const colors: Record<string, string> = {
    outlining: "bg-slate-600 text-slate-300",
    outlined: "bg-blue-600 text-blue-100",
    writing: "bg-amber-600 text-amber-100",
    completed: "bg-emerald-600 text-emerald-100",
  };
  const labels: Record<string, string> = {
    outlining: "大纲中",
    outlined: "已定纲",
    writing: "写作中",
    completed: "已完成",
  };
  return (
    <span className={`px-2 py-0.5 rounded text-[10px] ${colors[status] || "bg-slate-600"}`}>
      {labels[status] || status}
    </span>
  );
}
