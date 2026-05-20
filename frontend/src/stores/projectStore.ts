import { create } from "zustand";

export interface Novel {
  id: string;
  title: string;
  genre: string;
  target_chapters: number;
  status: string;
  current_chapter_index?: number;
}

interface ProjectStore {
  // Current project
  currentNovel: Novel | null;
  setCurrentNovel: (novel: Novel | null) => void;
  // Project list
  novels: Novel[];
  setNovels: (novels: Novel[]) => void;
}

export const useProjectStore = create<ProjectStore>((set) => ({
  currentNovel: null,
  setCurrentNovel: (novel) => set({ currentNovel: novel }),
  novels: [],
  setNovels: (novels) => set({ novels }),
}));
