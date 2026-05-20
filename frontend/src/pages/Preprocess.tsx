import { useState, useCallback, useRef, useEffect } from "react";
import { useParams } from "react-router-dom";
import { useAgentStore } from "../stores/agentStore";
import type { AgentStatus } from "../stores/agentStore";
import { useWS } from "../lib/useWS";

const AGENT_INFO: Record<string, { name: string; desc: string; outputKey: string }> = {
  A1: { name: "世界观完善", desc: "基于你的输入，构建完整自洽的世界体系", outputKey: "world_setting" },
  A3: { name: "角色完善", desc: "完善主角、配角、反派、NPC 的完整档案", outputKey: "character_system" },
  A2: { name: "风格完善", desc: "分析写作风格，生成可执行的风格参数", outputKey: "style_profile" },
  A4: { name: "大纲生成", desc: "聚合以上数据，生成全书章节大纲", outputKey: "novel_outline" },
};

// ── localStorage helpers (per-novel) ────────────────────

function storageKey(novelId: string): string {
  return `preprocess_${novelId}`;
}

function loadState(novelId: string | undefined) {
  if (!novelId) return null;
  try {
    const raw = localStorage.getItem(storageKey(novelId));
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
}

function saveState(novelId: string | undefined, state: Record<string, any>) {
  if (!novelId) return;
  try {
    localStorage.setItem(storageKey(novelId), JSON.stringify(state));
  } catch { /* quota exceeded, ignore */ }
}

const INPUT_DIMENSIONS = [
  {
    key: "world",
    label: "世界观",
    agent: "A1",
    placeholder: `请描述你的小说世界观构想，可以包括：

世界类型：修真 / 魔法 / 科幻 / 都市异能 / 末日 / 武侠 等
地理格局：大陆分布、城市、特殊地点
力量体系：修炼境界、魔法等级、科技水平
势力分布：宗门、国家、组织、种族
关键物品：法宝、科技、文物的设定
世界规则：禁忌、天道、物理法则
历史事件：重大历史事件和背景`,
  },
  {
    key: "characters",
    label: "角色",
    agent: "A3",
    placeholder: `请描述你的角色构想，可以包括：

主角：姓名、出身、性格、动机、成长方向
配角：与主角的关系、在故事中的功能
反派：动机、层次（不要纯恶人）
NPC：功能性角色设定
角色关系：恩怨、羁绊、冲突`,
  },
  {
    key: "style",
    label: "风格",
    agent: "A2",
    placeholder: `请描述你期望的写作风格，可以包括：

叙事视角：第一人称 / 第三人称有限 / 第三人称全知
情感基调：热血 / 冷峻 / 温情 / 暗黑 / 幽默 等
参考作品：类似《XXX》的风格
节奏偏好：快节奏打斗 / 慢热铺垫 / 张弛有度
对话风格：简洁 / 华丽 / 接地气
章节习惯：每章开头和结尾的偏好`,
  },
  {
    key: "outline",
    label: "大纲",
    agent: "A4",
    placeholder: `请描述你的大纲构想，可以包括：

故事主线：核心冲突和主线剧情
分卷结构：预计分几卷，每卷的主题
重要节点：关键转折点、高潮、结局
伏笔设计：想埋设的伏笔和悬念
角色弧线：主角的成长轨迹
章节预期：目标章节数`,
  },
];

type Phase = "input" | "running" | "complete";

export default function Preprocess() {
  const { id } = useParams<{ id: string }>();
  const { preprocessAgents, updateAgent, decisionPoint, setDecisionPoint } = useAgentStore();

  // Restore persisted state for this novel
  const saved = loadState(id);
  const [selectedAgent, setSelectedAgent] = useState(saved?.selectedAgent || "A1");
  const [activeTab, setActiveTab] = useState(saved?.activeTab || "world");
  const [phase, setPhase] = useState<Phase>(saved?.phase || "input");
  const [streamContent, setStreamContent] = useState<Record<string, string>>(saved?.streamContent || {});
  const [agentOutput, setAgentOutput] = useState<Record<string, any>>(saved?.agentOutput || {});
  const prevAgentRef = useRef<string | null>(saved?.prevAgent || null);

  const [inputs, setInputs] = useState<Record<string, string>>(
    saved?.inputs || { world: "", characters: "", style: "", outline: "" },
  );

  // Auto-save whenever state changes
  useEffect(() => {
    saveState(id, {
      selectedAgent, activeTab, phase, streamContent, agentOutput,
      prevAgent: prevAgentRef.current, inputs,
    });
  }, [id, selectedAgent, activeTab, phase, streamContent, agentOutput, inputs]);

  const wsUrl = id ? `/api/ws/preprocess/${id}` : null;

  const onMessage = useCallback(
    (msg: any) => {
      console.log("[Preprocess] 收到 WS 消息:", msg.type, msg);
      switch (msg.type) {
        case "pipeline_start":
          console.log("[Preprocess] 流水线启动，切换到 running 状态");
          setPhase("running");
          break;

        case "state_update": {
          const state = msg.state;
          const currentAgent = state.current_agent;
          const prevAgent = prevAgentRef.current;

          if (currentAgent && currentAgent !== prevAgent) {
            if (prevAgent) {
              updateAgent(prevAgent, { status: "complete", message: "完成" });
            }
            if (currentAgent !== "parse_input" && currentAgent !== "done") {
              updateAgent(currentAgent, { status: "running", message: `正在生成${AGENT_INFO[currentAgent]?.name || ""}...` });
            }
            prevAgentRef.current = currentAgent;
          }

          for (const [agentKey, info] of Object.entries(AGENT_INFO)) {
            const output = state[info.outputKey];
            if (output) {
              setAgentOutput((prev) => ({ ...prev, [agentKey]: output }));
            }
          }

          if (state.status === "asking" && state.decision_point) {
            const agent = state.current_agent;
            updateAgent(agent, { status: "asking" });
            setDecisionPoint({
              agent,
              question: state.decision_point.question,
              options: state.decision_point.options,
              recommendation: state.decision_point.recommendation,
            });
          }

          if (state.status === "complete") {
            updateAgent("A4", { status: "complete", message: "完成" });
          }
          break;
        }

        case "decision_point":
          updateAgent(msg.agent, { status: "asking" });
          setDecisionPoint({
            agent: msg.agent,
            ...msg.data,
          });
          break;

        case "agent_start":
        case "progress":
          if (msg.agent && msg.agent !== "input" && msg.agent !== "cross_validate") {
            updateAgent(msg.agent, {
              status: "running",
              message: msg.message,
            });
            if (msg.agent !== prevAgentRef.current) {
              prevAgentRef.current = msg.agent;
            }
          }
          break;

        case "stream":
          setStreamContent((prev) => ({
            ...prev,
            [msg.agent]: (prev[msg.agent] || "") + msg.content,
          }));
          break;

        case "agent_complete":
          updateAgent(msg.agent, { status: "complete", message: "完成" });
          setAgentOutput((prev) => ({ ...prev, [msg.agent]: msg.data }));
          break;

        case "pipeline_complete":
          setPhase("complete");
          if (msg.data) {
            for (const [agentKey, info] of Object.entries(AGENT_INFO)) {
              const output = msg.data[info.outputKey];
              if (output) {
                setAgentOutput((prev) => ({ ...prev, [agentKey]: output }));
              }
            }
          }
          break;

        case "error":
          console.error("WS error:", msg.message);
          if (prevAgentRef.current) {
            updateAgent(prevAgentRef.current, { status: "error", message: msg.message });
          }
          break;
      }
    },
    [updateAgent, setDecisionPoint],
  );

  const { send } = useWS(wsUrl, onMessage);

  const updateInput = (key: string, value: string) => {
    setInputs((prev) => ({ ...prev, [key]: value }));
  };

  const hasAnyInput = Object.values(inputs).some((v) => v.trim());

  const buildUserInput = () => {
    const parts: string[] = [];
    if (inputs.world.trim()) parts.push(`【世界观构想】\n${inputs.world}`);
    if (inputs.characters.trim()) parts.push(`【角色构想】\n${inputs.characters}`);
    if (inputs.style.trim()) parts.push(`【风格构想】\n${inputs.style}`);
    if (inputs.outline.trim()) parts.push(`【大纲构想】\n${inputs.outline}`);
    return parts.join("\n\n") || "请基于通用设定生成一部小说";
  };

  const startPipeline = () => {
    if (!id) {
      console.warn("[Preprocess] startPipeline 被调用但 id 为 null");
      return;
    }
    const payload = {
      action: "start",
      user_input: buildUserInput(),
      target_chapters: 100,
      user_world_setting: inputs.world,
      user_characters: inputs.characters,
      user_style: inputs.style,
      user_outline: inputs.outline,
    };
    console.log("[Preprocess] 开始流水线, novel_id:", id);
    console.log("[Preprocess] 发送 payload:", payload);
    console.log("[Preprocess] 各维度输入长度:", {
      world: inputs.world.length,
      characters: inputs.characters.length,
      style: inputs.style.length,
      outline: inputs.outline.length,
    });
    setAgentOutput({});
    setStreamContent({});
    prevAgentRef.current = null;
    send(payload);
  };

  const answerDecision = (choice: string) => {
    const answer = typeof choice === "object" ? JSON.stringify(choice) : choice;
    send({ action: "decide", answer });
    setDecisionPoint(null);
  };

  const agent = preprocessAgents.find((a) => a.agent === selectedAgent);

  return (
    <div className="flex h-[calc(100vh-48px)]">
      {/* Left: Agent panel */}
      <div className="w-80 border-r border-slate-700 bg-slate-800 p-4 flex flex-col gap-2">
        <h3 className="text-sm font-medium mb-2 text-slate-400">Agent 执行状态</h3>
        {preprocessAgents.map((a) => (
          <button
            key={a.agent}
            onClick={() => setSelectedAgent(a.agent)}
            className={`text-left p-3 rounded-lg border transition-colors ${
              selectedAgent === a.agent
                ? "border-indigo-500 bg-slate-700"
                : "border-slate-700 bg-slate-800 hover:border-slate-600"
            }`}
          >
            <div className="flex items-center gap-2">
              <StatusBadge status={a.status} />
              <div>
                <span className="text-sm font-medium">
                  {a.agent} - {AGENT_INFO[a.agent]?.name}
                </span>
                {a.message && (
                  <p className="text-xs text-slate-400 mt-0.5">{a.message}</p>
                )}
              </div>
            </div>
          </button>
        ))}
      </div>

      {/* Right: Content area */}
      <div className="flex-1 p-6 overflow-y-auto">
        {phase === "input" && (
          <div className="max-w-3xl mx-auto mt-8">
            <h2 className="text-xl font-medium mb-1">预处理 - 输入你的小说构想</h2>
            <p className="text-sm text-slate-400 mb-6">
              在下方四个维度中填写你的构想（填写越多，Agent 生成越精准）。全部填完后点击"开始分析"，Agent 会并行完善所有维度。
            </p>

            {/* Dimension tabs */}
            <div className="flex gap-1 mb-0">
              {INPUT_DIMENSIONS.map((dim) => (
                <button
                  key={dim.key}
                  onClick={() => setActiveTab(dim.key)}
                  className={`px-4 py-2 text-sm rounded-t-lg transition-colors ${
                    activeTab === dim.key
                      ? "bg-slate-800 text-white border-t border-x border-slate-700"
                      : "bg-slate-900 text-slate-500 hover:text-slate-300"
                  } ${inputs[dim.key].trim() ? "after:content-['_●'] after:text-indigo-400 after:text-[8px] after:ml-1 after:align-super" : ""}`}
                >
                  {dim.label}
                </button>
              ))}
            </div>

            {/* Active tab input */}
            {INPUT_DIMENSIONS.map((dim) => (
              <div
                key={dim.key}
                className={`${activeTab === dim.key ? "block" : "hidden"}`}
              >
                <textarea
                  value={inputs[dim.key]}
                  onChange={(e) => updateInput(dim.key, e.target.value)}
                  placeholder={dim.placeholder}
                  rows={14}
                  className="w-full bg-slate-800 border border-slate-700 rounded-b-lg rounded-tr-lg p-4 text-sm outline-none focus:border-indigo-500 resize-none"
                />
              </div>
            ))}

            {/* Quick overview of all filled dimensions */}
            <div className="mt-4 grid grid-cols-4 gap-3">
              {INPUT_DIMENSIONS.map((dim) => (
                <div
                  key={dim.key}
                  className={`p-3 rounded-lg border text-xs cursor-pointer transition-colors ${
                    activeTab === dim.key
                      ? "border-indigo-500 bg-slate-800"
                      : inputs[dim.key].trim()
                        ? "border-emerald-700 bg-slate-800"
                        : "border-slate-700 bg-slate-800/50"
                  }`}
                  onClick={() => setActiveTab(dim.key)}
                >
                  <div className="font-medium mb-1">{dim.label}</div>
                  <div className="text-slate-500">
                    {inputs[dim.key].trim()
                      ? `已填写 ${inputs[dim.key].length} 字`
                      : "待填写"}
                  </div>
                </div>
              ))}
            </div>

            <button
              onClick={startPipeline}
              disabled={!hasAnyInput}
              className="mt-6 bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 disabled:cursor-not-allowed text-white rounded px-6 py-2.5 text-sm font-medium transition-colors"
            >
              开始分析 — Agent 将并行完善所有维度
            </button>
          </div>
        )}

        {phase === "running" && decisionPoint && (
          <DecisionView dp={decisionPoint as any} onChoose={answerDecision} />
        )}

        {phase === "running" && !decisionPoint && (
          <div className="max-w-3xl mx-auto mt-8">
            {/* Overall progress tracker */}
            <div className="mb-8">
              <h2 className="text-lg font-medium mb-4">预处理进行中</h2>
              <div className="grid grid-cols-4 gap-3">
                {preprocessAgents.map((a) => {
                  const info = AGENT_INFO[a.agent];
                  const isRunning = a.status === "running";
                  const isDone = a.status === "complete";
                  const isAsking = a.status === "asking";
                  return (
                    <div
                      key={a.agent}
                      className={`p-4 rounded-lg border transition-colors ${
                        isRunning
                          ? "border-blue-500 bg-blue-500/10"
                          : isDone
                            ? "border-emerald-600 bg-emerald-500/10"
                            : isAsking
                              ? "border-amber-500 bg-amber-500/10"
                              : "border-slate-700 bg-slate-800"
                      }`}
                    >
                      <div className="flex items-center gap-2 mb-1">
                        {isRunning && <Spinner />}
                        {isDone && <span className="text-emerald-400 text-sm">✓</span>}
                        {isAsking && <span className="text-amber-400 text-sm">?</span>}
                        {a.status === "pending" && <span className="w-3 h-3 rounded-full bg-slate-600 inline-block" />}
                        <span className="text-sm font-medium">
                          {a.agent}
                        </span>
                      </div>
                      <div className="text-xs text-slate-400">{info?.name}</div>
                      <div className="text-xs text-slate-500 mt-1">
                        {isRunning ? a.message || "执行中..." : isDone ? "已完成" : isAsking ? "需要决策" : "等待中"}
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>

            {/* Active agent streaming / output */}
            <div>
              <div className="flex items-center gap-3 mb-3">
                <h3 className="text-md font-medium">
                  {AGENT_INFO[selectedAgent]?.name || "Agent"}
                </h3>
                {agent?.status === "running" && (
                  <span className="text-xs text-blue-400 flex items-center gap-1">
                    <Spinner /> 生成中...
                  </span>
                )}
                {agent?.status === "complete" && (
                  <span className="text-xs text-emerald-400">已完成</span>
                )}
              </div>
              <div className="bg-slate-800 border border-slate-700 rounded-lg p-4 min-h-[300px] max-h-[50vh] overflow-y-auto">
                {agent?.status === "pending" ? (
                  <div className="flex flex-col items-center justify-center h-[250px] text-slate-500">
                    <svg className="w-10 h-10 mb-3 opacity-30" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M12 6v6h4.5m4.5 0a9 9 0 1 1-18 0 9 9 0 0 1 18 0Z" />
                    </svg>
                    <p className="text-sm">等待前面 Agent 完成...</p>
                  </div>
                ) : streamContent[selectedAgent] ? (
                  <pre className="text-sm text-slate-400 whitespace-pre-wrap font-sans">
                    {streamContent[selectedAgent]}
                  </pre>
                ) : agent?.status === "running" ? (
                  <div className="flex flex-col items-center justify-center h-[250px]">
                    <div className="flex gap-1.5 mb-4">
                      <span className="w-2 h-2 bg-indigo-400 rounded-full animate-bounce" style={{ animationDelay: "0ms" }} />
                      <span className="w-2 h-2 bg-indigo-400 rounded-full animate-bounce" style={{ animationDelay: "150ms" }} />
                      <span className="w-2 h-2 bg-indigo-400 rounded-full animate-bounce" style={{ animationDelay: "300ms" }} />
                    </div>
                    <p className="text-sm text-slate-400">{agent?.message || "正在调用 LLM 生成..."}</p>
                    <p className="text-xs text-slate-500 mt-1">可能需 20-90 秒，请耐心等待</p>
                  </div>
                ) : agentOutput[selectedAgent] ? (
                  <pre className="text-sm text-slate-400 whitespace-pre-wrap font-mono max-h-[400px] overflow-y-auto">
                    {JSON.stringify(agentOutput[selectedAgent], null, 2)}
                  </pre>
                ) : (
                  <p className="text-sm text-slate-500">等待输出...</p>
                )}
              </div>
            </div>
          </div>
        )}

        {phase === "complete" && (
          <div className="max-w-2xl mx-auto mt-12 text-center">
            <div className="text-4xl mb-4">✅</div>
            <h2 className="text-xl font-medium mb-2">预处理完成</h2>
            <p className="text-sm text-slate-400 mb-6">
              世界观、角色、风格、大纲已全部生成。在下方切换 Agent 查看各维度输出，或前往大纲页面审核。
            </p>
            <div className="flex gap-2 justify-center mb-6">
              {Object.entries(AGENT_INFO).map(([key, info]) => (
                <button
                  key={key}
                  onClick={() => setSelectedAgent(key)}
                  className={`px-3 py-1.5 text-xs rounded ${
                    selectedAgent === key
                      ? "bg-indigo-600 text-white"
                      : "bg-slate-700 text-slate-400 hover:text-slate-200"
                  }`}
                >
                  {info.name}
                </button>
              ))}
            </div>
            {agentOutput[selectedAgent] ? (
              <div className="text-left bg-slate-800 border border-emerald-700 rounded-lg p-4 max-h-[400px] overflow-y-auto">
                <div className="text-xs text-emerald-400 mb-2">{AGENT_INFO[selectedAgent]?.name} 输出</div>
                <pre className="text-xs text-slate-400 whitespace-pre-wrap font-mono">
                  {JSON.stringify(agentOutput[selectedAgent], null, 2)}
                </pre>
              </div>
            ) : (
              <p className="text-sm text-slate-500">该 Agent 暂无输出数据</p>
            )}
            <a
              href={`/project/${id}/outline`}
              className="inline-block mt-4 bg-indigo-600 hover:bg-indigo-500 text-white rounded px-6 py-2 text-sm font-medium transition-colors"
            >
              查看大纲
            </a>
          </div>
        )}
      </div>
    </div>
  );
}

function Spinner() {
  return (
    <svg className="w-3.5 h-3.5 animate-spin text-blue-400" viewBox="0 0 24 24" fill="none">
      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
    </svg>
  );
}

function StatusBadge({ status }: { status: AgentStatus["status"] }) {
  const colors: Record<string, string> = {
    pending: "bg-slate-600",
    running: "bg-blue-500 animate-pulse",
    asking: "bg-amber-500 animate-pulse",
    complete: "bg-emerald-500",
    error: "bg-red-500",
  };
  return <span className={`w-2 h-2 rounded-full flex-shrink-0 ${colors[status]}`} />;
}

function DecisionView({
  dp,
  onChoose,
}: {
  dp: any;
  onChoose: (choice: string) => void;
}) {
  return (
    <div className="max-w-2xl">
      <h2 className="text-lg font-medium mb-1">
        {AGENT_INFO[dp.agent]?.name} - 需要你的决定
      </h2>
      <p className="text-sm text-slate-400 mb-2">{dp.question}</p>
      {dp.recommendation && (
        <div className="bg-indigo-900/30 border border-indigo-800 rounded-lg p-3 mb-4">
          <span className="text-xs text-indigo-400 font-medium">推荐</span>
          <p className="text-sm text-slate-300">{dp.recommendation.label}</p>
          <p className="text-xs text-slate-500">{dp.recommendation.reason}</p>
        </div>
      )}
      <div className="flex flex-col gap-2">
        {dp.options?.map((opt: any) => (
          <button
            key={opt.label}
            onClick={() => onChoose(opt.label)}
            className="text-left p-4 bg-slate-800 border border-slate-700 rounded-lg hover:border-indigo-500 transition-colors"
          >
            <div className="text-sm font-medium">{opt.label}</div>
            <div className="text-xs text-slate-400 mt-1">{opt.description}</div>
            {opt.consequence && (
              <div className="text-xs text-slate-500 mt-1">{opt.consequence}</div>
            )}
          </button>
        ))}
      </div>
      {dp.recommendation && (
        <button
          onClick={() => onChoose(dp.recommendation.label)}
          className="mt-3 text-sm text-indigo-400 hover:text-indigo-300"
        >
          跳过，按推荐继续
        </button>
      )}
    </div>
  );
}
