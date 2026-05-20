import { create } from "zustand";

export interface AgentStatus {
  agent: string;
  status: "pending" | "running" | "asking" | "complete" | "error";
  message?: string;
}

export interface DecisionPoint {
  agent: string;
  question: string;
  options: {
    label: string;
    description: string;
    consequence: string;
  }[];
  recommendation: {
    label: string;
    reason: string;
  };
}

interface AgentStore {
  // Preprocess agents
  preprocessAgents: AgentStatus[];
  setPreprocessAgents: (agents: AgentStatus[]) => void;
  updateAgent: (agent: string, update: Partial<AgentStatus>) => void;
  // Decision points
  decisionPoint: DecisionPoint | null;
  setDecisionPoint: (dp: DecisionPoint | null) => void;
  // Write agents (A5-A7)
  writeAgents: AgentStatus[];
  setWriteAgents: (agents: AgentStatus[]) => void;
}

export const useAgentStore = create<AgentStore>((set) => ({
  preprocessAgents: [
    { agent: "A1", status: "pending" },
    { agent: "A2", status: "pending" },
    { agent: "A3", status: "pending" },
    { agent: "A4", status: "pending" },
  ],
  setPreprocessAgents: (agents) => set({ preprocessAgents: agents }),
  updateAgent: (agentName, update) =>
    set((state) => ({
      preprocessAgents: state.preprocessAgents.map((a) =>
        a.agent === agentName ? { ...a, ...update } : a
      ),
    })),
  decisionPoint: null,
  setDecisionPoint: (dp) => set({ decisionPoint: dp }),
  writeAgents: [
    { agent: "A5", status: "pending" },
    { agent: "A6", status: "pending" },
    { agent: "A7", status: "pending" },
  ],
  setWriteAgents: (agents) => set({ writeAgents: agents }),
}));
