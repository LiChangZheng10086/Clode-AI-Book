import { useState, useCallback, useEffect, useRef } from "react";
import { useParams, Link } from "react-router-dom";
import { useAgentStore } from "../stores/agentStore";
import { useWS } from "../lib/useWS";
import { api } from "../lib/api";

const AGENT_NAMES: Record<string, string> = {
  A5: "章节大纲生成",
  A6: "章节内容生成",
  A7: "章节审核",
};

const HOOK_TYPE_LABELS: Record<string, string> = {
  mystery: "悬疑",
  chekhovs_gun: "契诃夫之枪",
  prophecy: "预言",
  secret: "秘密",
  conflict: "冲突",
};

type WriteTab = "outline" | "content" | "review";
type WriteStatus = "idle" | "outlining" | "writing" | "reviewing" | "done" | "stuck";

export default function Write() {
  const { id } = useParams<{ id: string }>();
  const { writeAgents } = useAgentStore();
  const [tab, setTab] = useState<WriteTab>("outline");
  const [status, setStatus] = useState<WriteStatus>("idle");
  const [chapterIndex, setChapterIndex] = useState(1);
  const [outline, setOutline] = useState<any>(null);
  const [content, setContent] = useState("");
  const [reviewReport, setReviewReport] = useState<any>(null);
  const [reviewRound, setReviewRound] = useState(0);
  const [streamText, setStreamText] = useState("");
  const [saving, setSaving] = useState(false);
  const [saveMsg, setSaveMsg] = useState("");
  const [writeDecision, setWriteDecision] = useState<any>(null);

  // Context data for the sidebar
  const [context, setContext] = useState<{
    book_summary: string;
    volume_summary: string;
    prev_chapter_recap: string;
    pending_hooks: any[];
    characters_involved: string[];
    entity_states: any[];
  }>({
    book_summary: "",
    volume_summary: "",
    prev_chapter_recap: "",
    pending_hooks: [],
    characters_involved: [],
    entity_states: [],
  });

  const fetchContext = useCallback(() => {
    if (id) {
      api.chapters.getWriteContext(id, chapterIndex)
        .then(setContext)
        .catch(console.error);
    }
  }, [id, chapterIndex]);

  const fetchContextRef = useRef(fetchContext);
  fetchContextRef.current = fetchContext;

  // Fetch context on mount and when chapter changes
  useEffect(() => { fetchContext(); }, [fetchContext]);

  // Load existing chapter data when returning to a chapter
  useEffect(() => {
    if (!id) return;
    api.chapters.getByIndex(id, chapterIndex)
      .then((ch: any) => {
        if (ch.outline) setOutline(ch.outline);
        if (ch.content) setContent(ch.content);
        if (ch.status === "completed") setStatus("done");
      })
      .catch(() => {}); // Chapter may not exist yet
  }, [id, chapterIndex]);

  const wsUrl = id ? `/api/ws/write/${id}` : null;

  const onMessage = useCallback((msg: any) => {
    switch (msg.type) {
      case "state_update":
        const s = msg.state;
        if (s.chapter_outline && s.status === "outline_done") {
          setOutline(s.chapter_outline);
          setStatus("idle");
        }
        if (s.polished_content) {
          setContent(s.polished_content);
          setTab("content");
        }
        if (s.review_report) {
          setReviewReport(s.review_report);
          setReviewRound(s.review_round);
          if (s.review_report.overall === "pass") {
            setStatus("done");
          } else if (s.review_round >= 3) {
            setStatus("stuck");
          }
          setTab("review");
        }
        break;

      case "agent_start":
        if (msg.agent === "A5") setStatus("outlining");
        if (msg.agent === "A6") setStatus("writing");
        if (msg.agent === "A7") setStatus("reviewing");
        setStreamText("");
        break;

      case "agent_complete":
        if (msg.agent === "A5" && msg.data) {
          setOutline(msg.data);
          setStatus("idle");
          setTab("outline");
        }
        if (msg.agent === "A6") setTab("content");
        break;

      case "content_stream":
        setStreamText(msg.content);
        break;

      case "review_report":
        setReviewReport(msg.data);
        setTab("review");
        break;

      case "pipeline_complete":
        setStatus("done");
        setContent(msg.data?.polished_content || content);
        setReviewReport(msg.data?.review_report || reviewReport);
        setTab("content");
        fetchContextRef.current(); // Refresh summaries/hooks after write completes
        break;

      case "pipeline_stuck":
        setStatus("stuck");
        setContent(msg.data?.polished_content || content);
        setReviewReport(msg.data?.review_report || reviewReport);
        break;

      case "review_retry":
        setReviewReport(msg.data);
        setReviewRound((r) => r + 1);
        setTab("review");
        break;

      case "decision_point":
        console.log("[Write] Decision point received:", msg);
        setWriteDecision({ ...msg.data, agent: msg.agent });
        setStatus("idle");
        if (msg.data?.outline) {
          setOutline(msg.data.outline);
        }
        break;

      case "error":
        console.error("Write WS error:", msg.message);
        break;
    }
  }, []);

  const { send } = useWS(wsUrl, onMessage);

  const startOutline = () => {
    setStatus("outlining");
    send({
      action: "start_outline",
      chapter_id: `${id}_ch${chapterIndex}`,
      chapter_index: chapterIndex,
      context_package: {},
    });
  };

  const confirmOutline = () => {
    setStatus("writing");
    send({
      action: "start_write",
      chapter_id: `${id}_ch${chapterIndex}`,
      chapter_index: chapterIndex,
      novel_outline_beat: outline,
      context_package: {},
    });
  };

  const retryAfterReview = () => {
    setStatus("writing");
    send({
      action: "start_write",
      chapter_id: `${id}_ch${chapterIndex}`,
      chapter_index: chapterIndex,
      novel_outline_beat: outline,
      context_package: { review_report: reviewReport },
    });
  };

  const manualApprove = () => {
    send({ action: "confirm_manual", chapter_id: `${id}_ch${chapterIndex}` });
    setStatus("done");
  };

  const handleSave = async () => {
    if (!id) return;
    setSaving(true);
    setSaveMsg("");
    try {
      await api.chapters.saveContent(id, chapterIndex, { content, outline });
      setSaveMsg("保存成功");
      setTimeout(() => setSaveMsg(""), 3000);
    } catch (e: any) {
      setSaveMsg(`保存失败: ${e.message}`);
    } finally {
      setSaving(false);
    }
  };

  const answerDecision = (choice: string) => {
    const answer = typeof choice === "string" ? choice : JSON.stringify(choice);
    send({
      action: "decide",
      chapter_id: `${id}_ch${chapterIndex}`,
      answer,
    });
    setWriteDecision(null);
    if (choice.includes("确认")) {
      setStatus("writing");
    } else if (choice.includes("重新生成")) {
      setOutline(null);
      setStatus("outlining");
    }
  };

  const nextChapter = () => {
    setChapterIndex((c) => c + 1);
    setOutline(null);
    setContent("");
    setReviewReport(null);
    setReviewRound(0);
    setStreamText("");
    setStatus("idle");
    setTab("outline");
    setWriteDecision(null);
  };

  return (
    <div className="flex h-[calc(100vh-48px)]">
      {/* Left: Context panel */}
      <div className="w-80 border-r border-slate-700 bg-slate-800 p-4 overflow-y-auto flex flex-col gap-3">
        <h3 className="text-sm font-medium text-slate-400">上下文</h3>

        <CollapsibleSection title="全书摘要">
          {context.book_summary ? (
            <p className="text-xs text-slate-300 leading-relaxed">{context.book_summary}</p>
          ) : (
            <p className="text-xs text-slate-500">尚未生成全书摘要，请先完成章节写作。</p>
          )}
        </CollapsibleSection>
        <CollapsibleSection title="当前卷摘要">
          {context.volume_summary ? (
            <p className="text-xs text-slate-300 leading-relaxed">{context.volume_summary}</p>
          ) : (
            <p className="text-xs text-slate-500">—</p>
          )}
        </CollapsibleSection>
        <CollapsibleSection title="前章回顾">
          {context.prev_chapter_recap ? (
            <p className="text-xs text-slate-300 leading-relaxed">{context.prev_chapter_recap}</p>
          ) : (
            <p className="text-xs text-slate-500">{chapterIndex <= 1 ? "这是第一章，无前章回顾。" : "暂无前章摘要。"}</p>
          )}
        </CollapsibleSection>
        <CollapsibleSection title="待回收钩子">
          {context.pending_hooks.length > 0 ? (
            <div className="space-y-2">
              {context.pending_hooks.map((h: any) => (
                <div key={h.id} className="bg-slate-700/50 rounded p-2">
                  <div className="flex items-center gap-1.5 mb-0.5">
                    <span className={`text-[10px] px-1 rounded ${
                      h.priority === "major" ? "bg-red-700/50 text-red-300" : "bg-slate-600 text-slate-400"
                    }`}>
                      {h.priority === "major" ? "主线" : "次要"}
                    </span>
                    <span className="text-[10px] text-slate-500">
                      {HOOK_TYPE_LABELS[h.hook_type] || h.hook_type}
                    </span>
                    <span className="text-[10px] text-slate-500">第{h.planted_chapter_index}章埋下</span>
                  </div>
                  <p className="text-xs text-slate-300">{h.description}</p>
                </div>
              ))}
            </div>
          ) : (
            <p className="text-xs text-slate-500">暂无待回收的伏笔。</p>
          )}
        </CollapsibleSection>
        <CollapsibleSection title="本章涉及角色">
          {context.characters_involved.length > 0 ? (
            <div className="flex flex-wrap gap-1">
              {context.characters_involved.map((name) => (
                <span key={name} className="text-xs bg-slate-700 px-2 py-0.5 rounded text-slate-300">
                  {name}
                </span>
              ))}
            </div>
          ) : outline?.scenes?.length > 0 ? (
            <div className="flex flex-wrap gap-1">
              {(() => {
                const names = new Set<string>();
                outline.scenes.forEach((s: any) => {
                  const chars = s.characters_involved || s.characters || [];
                  chars.forEach((c: any) => names.add(typeof c === "string" ? c : c.name));
                });
                return [...names].map((name) => (
                  <span key={name} className="text-xs bg-slate-700 px-2 py-0.5 rounded text-slate-300">
                    {name}
                  </span>
                ));
              })()}
            </div>
          ) : (
            <p className="text-xs text-slate-500">生成章节大纲后将显示涉及角色。</p>
          )}
        </CollapsibleSection>
      </div>

      {/* Right: Main area */}
      <div className="flex-1 flex flex-col">
        {/* Status bar */}
        <div className="flex items-center gap-3 px-4 py-2 bg-slate-800 border-b border-slate-700">
          {writeAgents.map((a) => (
            <div key={a.agent} className="flex items-center gap-1.5">
              <span
                className={`w-1.5 h-1.5 rounded-full ${
                  (a.agent === "A5" && status === "outlining") ||
                  (a.agent === "A6" && (status === "writing" || status === "idle")) ||
                  (a.agent === "A7" && (status === "reviewing" || status === "done"))
                    ? "bg-blue-500 animate-pulse"
                    : "bg-slate-600"
                }`}
              />
              <span className="text-xs text-slate-400">
                {a.agent} {AGENT_NAMES[a.agent]}
              </span>
            </div>
          ))}
          <div className="ml-auto text-xs text-slate-500">
            审核轮次: {reviewRound}/3
          </div>
          <div className="flex items-center gap-2 ml-4">
            <button
              onClick={() => setChapterIndex((c) => Math.max(1, c - 1))}
              className="text-xs text-slate-500 hover:text-slate-300 px-1"
            >
              ◀
            </button>
            <span className="text-xs text-slate-300">第{chapterIndex}章</span>
            <button
              onClick={() => setChapterIndex((c) => c + 1)}
              className="text-xs text-slate-500 hover:text-slate-300 px-1"
            >
              ▶
            </button>
          </div>
        </div>

        {/* Tabs */}
        <div className="flex gap-2 px-4 pt-3 pb-2 border-b border-slate-700">
          {[
            { key: "outline", label: "章节大纲" },
            { key: "content", label: "正文" },
            { key: "review", label: "审核报告" },
          ].map((t) => (
            <button
              key={t.key}
              onClick={() => setTab(t.key as WriteTab)}
              className={`px-3 py-1 text-sm rounded ${
                tab === t.key
                  ? "bg-indigo-600 text-white"
                  : "bg-slate-800 text-slate-400 hover:text-slate-200"
              }`}
            >
              {t.label}
            </button>
          ))}
        </div>

        {/* Tab content */}
        <div className="flex-1 p-6 overflow-y-auto">
          {tab === "outline" && (
            <div>
              {writeDecision ? (
                <div>
                  <WriteDecisionView
                    dp={writeDecision}
                    outline={outline}
                    onChoose={answerDecision}
                  />
                </div>
              ) : outline ? (
                <div>
                  <div className="bg-slate-800 border border-slate-700 rounded-lg p-4">
                    <pre className="text-sm text-slate-400 whitespace-pre-wrap font-sans">
                      {JSON.stringify(outline, null, 2)}
                    </pre>
                  </div>
                  <div className="mt-4 flex gap-2">
                    <button
                      onClick={confirmOutline}
                      disabled={status !== "idle"}
                      className="bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 text-white rounded px-4 py-2 text-sm"
                    >
                      确认大纲，开始写作
                    </button>
                    <button
                      onClick={startOutline}
                      className="bg-slate-700 hover:bg-slate-600 text-slate-200 rounded px-4 py-2 text-sm"
                    >
                      重新生成
                    </button>
                  </div>
                </div>
              ) : (
                <div className="text-center mt-20">
                  <p className="text-sm text-slate-400 mb-4">尚未生成章节大纲</p>
                  <button
                    onClick={startOutline}
                    disabled={status === "outlining"}
                    className="bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 text-white rounded px-6 py-2 text-sm"
                  >
                    {status === "outlining" ? "生成中..." : "生成章节大纲"}
                  </button>
                  {streamText && (
                    <div className="mt-4 bg-slate-800 border border-slate-700 rounded-lg p-4 text-left">
                      <pre className="text-sm text-slate-400 whitespace-pre-wrap font-sans">
                        {streamText}
                      </pre>
                    </div>
                  )}
                </div>
              )}
            </div>
          )}

          {tab === "content" && (
            <div>
              {content ? (
                <div>
                  <div className="bg-slate-800 border border-slate-700 rounded-lg p-6 min-h-[400px]">
                    <div className="text-sm text-slate-300 leading-relaxed whitespace-pre-wrap font-sans">
                      {content}
                    </div>
                  </div>
                  <div className="mt-4 flex gap-2 items-center">
                    <button
                      onClick={handleSave}
                      disabled={saving}
                      className="bg-emerald-600 hover:bg-emerald-500 disabled:opacity-50 text-white rounded px-4 py-2 text-sm"
                    >
                      {saving ? "保存中..." : "保存正文"}
                    </button>
                    {saveMsg && (
                      <span className={`text-xs ${saveMsg.startsWith("保存失败") ? "text-red-400" : "text-emerald-400"}`}>
                        {saveMsg}
                      </span>
                    )}
                  </div>
                </div>
              ) : status === "writing" ? (
                <div className="text-center mt-20">
                  <p className="text-sm text-slate-400 mb-2">正在撰写...</p>
                  {streamText && (
                    <div className="bg-slate-800 border border-slate-700 rounded-lg p-4 text-left max-h-[400px] overflow-y-auto">
                      <pre className="text-sm text-slate-400 whitespace-pre-wrap font-sans">
                        {streamText}
                      </pre>
                    </div>
                  )}
                </div>
              ) : (
                <div className="text-center mt-20">
                  <p className="text-sm text-slate-400">请先生成并确认章节大纲</p>
                </div>
              )}
            </div>
          )}

          {tab === "review" && (
            <div>
              {reviewReport ? (
                <div>
                  <div className="grid grid-cols-2 gap-2 mb-4">
                    {Object.entries(reviewReport.scores || {}).map(([key, score]: [string, any]) => (
                      <div key={key} className="bg-slate-800 border border-slate-700 rounded p-3">
                        <div className="text-xs text-slate-400 mb-1">{key}</div>
                        <div className="flex items-center gap-2">
                          <div className="flex-1 h-1.5 bg-slate-700 rounded-full overflow-hidden">
                            <div
                              className={`h-full rounded-full ${
                                score >= 7 ? "bg-emerald-500" : score >= 5 ? "bg-amber-500" : "bg-red-500"
                              }`}
                              style={{ width: `${score * 10}%` }}
                            />
                          </div>
                          <span className="text-xs text-slate-300">{score}/10</span>
                        </div>
                      </div>
                    ))}
                  </div>

                  <div className="mb-2 flex items-center gap-2">
                    <span className="text-sm font-medium">
                      {reviewReport.overall === "pass" ? "✅ 审核通过" : "⚠️ 需要修改"}
                    </span>
                  </div>

                  {reviewReport.issues?.map((issue: any, i: number) => (
                    <div
                      key={i}
                      className={`mb-3 rounded-lg p-4 ${
                        issue.severity === "major"
                          ? "bg-red-900/20 border border-red-800"
                          : "bg-amber-900/20 border border-amber-800"
                      }`}
                    >
                      <div className="flex items-center gap-2 mb-1">
                        <span
                          className={`text-xs px-2 py-0.5 rounded ${
                            issue.severity === "major"
                              ? "bg-red-800 text-red-300"
                              : "bg-amber-800 text-amber-300"
                          }`}
                        >
                          {issue.severity}
                        </span>
                        <span className="text-xs text-slate-400">{issue.dimension}</span>
                        {issue.location && (
                          <span className="text-xs text-slate-500">— {issue.location}</span>
                        )}
                      </div>
                      <p className="text-sm text-slate-300 mb-1">{issue.problem}</p>
                      {issue.suggestion && (
                        <p className="text-xs text-slate-400">→ {issue.suggestion}</p>
                      )}
                    </div>
                  ))}

                  <div className="mt-4 flex gap-2">
                    {reviewReport.overall !== "pass" && reviewRound < 3 && (
                      <button
                        onClick={retryAfterReview}
                        className="bg-indigo-600 hover:bg-indigo-500 text-white rounded px-4 py-2 text-sm"
                      >
                        自动修正 (第{reviewRound + 1}轮)
                      </button>
                    )}
                    {status === "stuck" && (
                      <button
                        onClick={manualApprove}
                        className="bg-amber-600 hover:bg-amber-500 text-white rounded px-4 py-2 text-sm"
                      >
                        人工通过
                      </button>
                    )}
                    <button
                      onClick={handleSave}
                      disabled={saving}
                      className="bg-emerald-600 hover:bg-emerald-500 disabled:opacity-50 text-white rounded px-4 py-2 text-sm"
                    >
                      {saving ? "保存中..." : "保存正文"}
                    </button>
                    {saveMsg && (
                      <span className={`text-xs self-center ${saveMsg.startsWith("保存失败") ? "text-red-400" : "text-emerald-400"}`}>
                        {saveMsg}
                      </span>
                    )}
                  </div>
                </div>
              ) : (
                <div className="text-center mt-20">
                  <p className="text-sm text-slate-400">暂无审核报告</p>
                </div>
              )}
            </div>
          )}

          {/* Bottom action bar */}
          {status === "done" && (
            <div className="mt-6 border-t border-slate-700 pt-4 flex justify-between items-center">
              <div className="flex items-center gap-4">
                <span className="text-sm text-emerald-400">✅ 本章通过审核</span>
                <Link
                  to={`/project/${id}/write/${chapterIndex}`}
                  className="text-xs text-indigo-400 hover:text-indigo-300"
                >
                  在阅读器中查看 →
                </Link>
              </div>
              <button
                onClick={nextChapter}
                className="bg-indigo-600 hover:bg-indigo-500 text-white rounded px-6 py-2 text-sm"
              >
                下一章 →
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function CollapsibleSection({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <details className="group">
      <summary className="text-xs font-medium text-slate-400 cursor-pointer hover:text-slate-300 list-none select-none">
        {title}
      </summary>
      <div className="mt-2 ml-2">{children}</div>
    </details>
  );
}

function WriteDecisionView({
  dp,
  outline,
  onChoose,
}: {
  dp: any;
  outline: any;
  onChoose: (choice: string) => void;
}) {
  return (
    <div className="max-w-2xl">
      <div className="bg-amber-900/30 border border-amber-700 rounded-lg p-4 mb-4">
        <h2 className="text-lg font-medium text-amber-300 mb-1">
          关键章节 — 需要人工确认
        </h2>
        <p className="text-sm text-slate-300">{dp.question}</p>
        {dp.chapter_index && (
          <p className="text-xs text-slate-500 mt-1">第 {dp.chapter_index} 章</p>
        )}
      </div>

      {/* Show the outline for review */}
      {outline && (
        <div className="mb-4">
          <h3 className="text-sm font-medium text-slate-400 mb-2">章节大纲预览</h3>
          <div className="bg-slate-800 border border-slate-700 rounded-lg p-4 max-h-[40vh] overflow-y-auto">
            <pre className="text-xs text-slate-400 whitespace-pre-wrap font-sans">
              {JSON.stringify(outline, null, 2)}
            </pre>
          </div>
        </div>
      )}

      <div className="flex flex-col gap-2">
        {dp.options?.map((opt: any) => (
          <button
            key={opt.label}
            onClick={() => onChoose(opt.label)}
            className={`text-left p-4 bg-slate-800 border rounded-lg transition-colors ${
              opt.label.includes("确认")
                ? "border-indigo-500 hover:border-indigo-400"
                : "border-slate-700 hover:border-slate-600"
            }`}
          >
            <div className="text-sm font-medium text-slate-200">{opt.label}</div>
            <div className="text-xs text-slate-400 mt-1">{opt.description}</div>
          </button>
        ))}
      </div>

      <p className="mt-4 text-xs text-slate-500">
        这是关键剧情节点，建议仔细审核大纲中的场景安排、角色动机和伏笔处理后再确认。
      </p>
    </div>
  );
}
