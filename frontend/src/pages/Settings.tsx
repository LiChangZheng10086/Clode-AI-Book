import { useState, useEffect } from "react";
import { useParams } from "react-router-dom";
import { api } from "../lib/api";

type Tab = "world" | "characters" | "style";

/* ── Structured JSON renderer (no raw <pre> dumps) ── */

function JsonBlock({ data }: { data: unknown }) {
  if (data === null || data === undefined) return <span className="text-slate-500">暂无</span>;

  if (typeof data === "string") {
    return <span className="text-slate-300">{data}</span>;
  }

  if (typeof data === "number" || typeof data === "boolean") {
    return <span className="text-slate-300">{String(data)}</span>;
  }

  if (Array.isArray(data)) {
    return (
      <div className="space-y-2">
        {data.map((item, i) => (
          <div key={i} className="bg-slate-900 border border-slate-700 rounded p-3">
            <JsonBlock data={item} />
          </div>
        ))}
      </div>
    );
  }

  if (typeof data === "object") {
    const entries = Object.entries(data as Record<string, unknown>);
    if (entries.length === 0) return <span className="text-slate-500">—</span>;
    return (
      <div className="space-y-2">
        {entries.map(([key, val]) => (
          <div key={key}>
            <div className="text-xs font-medium text-indigo-400 mb-1">{formatKey(key)}</div>
            <div className="ml-2 text-sm">
              <JsonBlock data={val} />
            </div>
          </div>
        ))}
      </div>
    );
  }

  return <span className="text-slate-500">—</span>;
}

function formatKey(key: string): string {
  const labels: Record<string, string> = {
    world_type: "世界类型", era_background: "时代背景", geography: "地理格局",
    power_system: "力量体系", factions: "势力分布", items: "关键物品",
    rules: "世界规则", history: "重大历史", name: "名称", type: "类型",
    narrative_pov: "叙事视角", tense: "时态", tone: "情感基调",
    sentence: "句式", paragraph: "段落", dialogue: "对话",
    description: "描写", banned: "禁用项", chapter_structure: "章节结构",
    opening: "开头方式", closing: "结尾方式",
    avg_length_range: "平均长度范围", variance: "变化度", rhythm_note: "节奏说明",
    avg_sentences: "平均句数", dialogue_density: "对话密度",
    style: "风格", inner_monologue: "内心独白", inner_monologue_style: "独白风格",
    action_ratio: "动作比例", dialogue_ratio: "对话比例", exposition_ratio: "说明比例",
    show_vs_tell: "展示vs讲述", transitions: "禁用转折词", cliches: "禁用陈词",
    patterns: "禁用模式",
    appearance: "外貌", personality: "性格", background: "背景",
    motivation: "动机", flaws: "缺点",
  };
  return labels[key] || key;
}

/* ── Page ── */

export default function Settings() {
  const { id } = useParams<{ id: string }>();
  const [tab, setTab] = useState<Tab>("world");
  const [data, setData] = useState<any>(null);
  const [characters, setCharacters] = useState<any[]>([]);

  useEffect(() => {
    if (!id) return;
    if (tab === "world") {
      api.settings.getWorld(id).then(setData).catch(() => setData(null));
    } else if (tab === "characters") {
      api.characters.list(id).then(setCharacters).catch(console.error);
    } else if (tab === "style") {
      api.settings.getStyle(id).then(setData).catch(() => setData(null));
    }
  }, [tab, id]);

  const tabs: { key: Tab; label: string }[] = [
    { key: "world", label: "世界观" },
    { key: "characters", label: "角色" },
    { key: "style", label: "风格" },
  ];

  return (
    <div className="max-w-4xl mx-auto p-6">
      <div className="flex gap-1 mb-6">
        {tabs.map((t) => (
          <button
            key={t.key}
            onClick={() => setTab(t.key)}
            className={`px-4 py-2 text-sm rounded ${
              tab === t.key
                ? "bg-indigo-600 text-white"
                : "text-slate-400 hover:text-slate-200 hover:bg-slate-800"
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {/* ── World ── */}
      {tab === "world" && (
        <div className="bg-slate-800 border border-slate-700 rounded-lg p-6">
          <h2 className="font-medium mb-4">世界观设定</h2>
          {data?.settings ? (
            <JsonBlock data={data.settings} />
          ) : (
            <p className="text-sm text-slate-500">暂无世界观数据，请先运行预处理。</p>
          )}
        </div>
      )}

      {/* ── Characters ── */}
      {tab === "characters" && (
        <div>
          <div className="grid grid-cols-2 gap-4 mb-6">
            {characters.map((c) => (
              <div key={c.id} className="bg-slate-800 border border-slate-700 rounded-lg p-4">
                <div className="flex items-center gap-2 mb-2">
                  <span className="text-sm font-medium">{c.name}</span>
                  <RoleBadge role={c.role} />
                </div>
                {c.profile && typeof c.profile === "object" ? (
                  <div className="text-xs text-slate-400 space-y-1">
                    {c.profile.personality && (
                      <p>性格：{c.profile.personality}</p>
                    )}
                    {c.profile.background && (
                      <p className="line-clamp-2">背景：{c.profile.background}</p>
                    )}
                    {c.profile.motivation && (
                      <p className="line-clamp-2">动机：{c.profile.motivation}</p>
                    )}
                    {c.profile.appearance && (
                      <p>外貌：{c.profile.appearance}</p>
                    )}
                    {!c.profile.personality && !c.profile.background && !c.profile.motivation && (
                      <JsonBlock data={c.profile} />
                    )}
                  </div>
                ) : (
                  <p className="text-xs text-slate-500">暂无详情</p>
                )}
                {c.arc && Array.isArray(c.arc) && c.arc.length > 0 && (
                  <details className="mt-2 text-xs">
                    <summary className="text-indigo-400 cursor-pointer">成长弧线 ({c.arc.length} 阶段)</summary>
                    <div className="mt-1 space-y-1">
                      {c.arc.map((a: any, i: number) => (
                        <div key={i} className="text-slate-400">
                          <span className="text-slate-500">{a.chapter_range || a.stage}</span>
                          {a.description && <span> — {a.description}</span>}
                        </div>
                      ))}
                    </div>
                  </details>
                )}
              </div>
            ))}
          </div>
          {characters.length === 0 && (
            <p className="text-sm text-slate-500">暂无角色数据，请先运行预处理。</p>
          )}
        </div>
      )}

      {/* ── Style ── */}
      {tab === "style" && (
        <div className="bg-slate-800 border border-slate-700 rounded-lg p-6">
          <h2 className="font-medium mb-4">风格画像</h2>
          {data?.extracted_params ? (
            <JsonBlock data={data.extracted_params} />
          ) : (
            <p className="text-sm text-slate-500">暂无风格数据，请先运行预处理。</p>
          )}
        </div>
      )}
    </div>
  );
}

function RoleBadge({ role }: { role: string }) {
  const colors: Record<string, string> = {
    protagonist: "bg-amber-600 text-amber-100",
    antagonist: "bg-red-700 text-red-100",
    supporting: "bg-blue-600 text-blue-100",
    npc: "bg-slate-600 text-slate-300",
  };
  const labels: Record<string, string> = {
    protagonist: "主角",
    antagonist: "反派",
    supporting: "配角",
    npc: "NPC",
  };
  return (
    <span className={`text-xs px-2 py-0.5 rounded ${colors[role] || "bg-slate-700 text-slate-300"}`}>
      {labels[role] || role}
    </span>
  );
}
