import { useState, useEffect } from "react";
import { useParams } from "react-router-dom";
import { api } from "../lib/api";

const COLUMNS = [
  { key: "unresolved", title: "已播种", color: "border-blue-500" },
  { key: "in_progress", title: "推进中", color: "border-amber-500" },
  { key: "resolved", title: "已回收", color: "border-emerald-500" },
  { key: "overdue", title: "逾期", color: "border-red-500" },
];

const HOOK_TYPE_LABELS: Record<string, string> = {
  mystery: "悬念",
  chekhovs_gun: "契诃夫之枪",
  prophecy: "预言",
  secret: "角色秘密",
  conflict: "冲突种子",
};

export default function Hooks() {
  const { id } = useParams<{ id: string }>();
  const [hooks, setHooks] = useState<any[]>([]);

  useEffect(() => {
    if (id) api.hooks.list(id).then(setHooks).catch(console.error);
  }, [id]);

  const overdueHooks = hooks.filter(
    (h) => h.status !== "resolved" && h.status !== "abandoned"
    // In production: check if current chapter > target range end
  );

  const hooksByStatus = (status: string) => {
    if (status === "overdue") return overdueHooks;
    return hooks.filter((h) => h.status === status);
  };

  return (
    <div className="max-w-full mx-auto p-6">
      <div className="flex items-center justify-between mb-6">
        <h2 className="text-lg font-medium">钩子看板</h2>
        <span className="text-sm text-slate-400">
          共 {hooks.length} 个钩子 · 未回收 {hooks.filter((h) => h.status !== "resolved").length} 个
        </span>
      </div>

      <div className="grid grid-cols-4 gap-4">
        {COLUMNS.map((col) => (
          <div key={col.key} className="bg-slate-800 border border-slate-700 rounded-lg p-3">
            <div className={`text-xs font-medium mb-3 border-l-2 ${col.color} pl-2`}>
              {col.title} ({hooksByStatus(col.key).length})
            </div>
            <div className="flex flex-col gap-2 min-h-[200px]">
              {hooksByStatus(col.key).map((hook) => (
                <div
                  key={hook.id}
                  className="bg-slate-700/50 rounded-lg p-3 text-sm cursor-pointer hover:bg-slate-700 transition-colors"
                >
                  <div className="text-xs text-slate-500 mb-1">
                    #{hook.id.slice(0, 8)} · {HOOK_TYPE_LABELS[hook.hook_type] || hook.hook_type}
                  </div>
                  <div className="text-xs">{hook.description}</div>
                  <div className="text-xs text-slate-500 mt-1">
                    种于第{hook.planted_chapter_index}章
                    {hook.target_chapter_range &&
                      ` · 计划 ${hook.target_chapter_range[0]}-${hook.target_chapter_range[1]} 章回收`}
                  </div>
                </div>
              ))}
              {hooksByStatus(col.key).length === 0 && (
                <div className="text-xs text-slate-600 text-center py-4">暂无</div>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
