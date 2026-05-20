const BASE = "/api";

async function request<T>(url: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${url}`, {
    headers: { "Content-Type": "application/json", ...options?.headers },
    ...options,
  });
  if (!res.ok) {
    const error = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(error.detail || "Request failed");
  }
  if (res.status === 204) return undefined as T;
  return res.json();
}

export const api = {
  novels: {
    list: () => request<any[]>("/novels/"),
    create: (data: any) => request<any>("/novels/", { method: "POST", body: JSON.stringify(data) }),
    get: (id: string) => request<any>(`/novels/${id}`),
    update: (id: string, data: any) =>
      request<any>(`/novels/${id}`, { method: "PATCH", body: JSON.stringify(data) }),
    delete: (id: string) => request<void>(`/novels/${id}`, { method: "DELETE" }),
  },
  characters: {
    list: (novelId: string) => request<any[]>(`/characters/novel/${novelId}`),
    create: (novelId: string, data: any) =>
      request<any>(`/characters/novel/${novelId}`, { method: "POST", body: JSON.stringify(data) }),
    update: (id: string, data: any) =>
      request<any>(`/characters/${id}`, { method: "PATCH", body: JSON.stringify(data) }),
    delete: (id: string) => request<void>(`/characters/${id}`, { method: "DELETE" }),
  },
  chapters: {
    listVolumes: (novelId: string) => request<any[]>(`/chapters/novel/${novelId}/volumes`),
    list: (volumeId: string) => request<any[]>(`/chapters/volume/${volumeId}/chapters`),
    get: (id: string) => request<any>(`/chapters/${id}`),
    getWriteContext: (novelId: string, chapterIndex: number) =>
      request<any>(`/chapters/novel/${novelId}/write-context?chapter_index=${chapterIndex}`),
    getByIndex: (novelId: string, chapterIndex: number) =>
      request<any>(`/chapters/novel/${novelId}/chapter/${chapterIndex}`),
    saveContent: (novelId: string, chapterIndex: number, data: { content?: string; outline?: any }) =>
      request<any>(`/chapters/novel/${novelId}/chapter/${chapterIndex}/save`, { method: "PATCH", body: JSON.stringify(data) }),
    updateOutline: (id: string, outline: any) =>
      request<any>(`/chapters/${id}/outline`, { method: "PATCH", body: JSON.stringify({ outline }) }),
    updateContent: (id: string, content: string) =>
      request<any>(`/chapters/${id}/content`, { method: "PATCH", body: JSON.stringify({ content }) }),
  },
  hooks: {
    list: (novelId: string, params?: Record<string, string>) => {
      const qs = params ? "?" + new URLSearchParams(params).toString() : "";
      return request<any[]>(`/hooks/novel/${novelId}${qs}`);
    },
    create: (novelId: string, data: any) =>
      request<any>(`/hooks/novel/${novelId}`, { method: "POST", body: JSON.stringify(data) }),
    update: (id: string, data: any) =>
      request<any>(`/hooks/${id}`, { method: "PATCH", body: JSON.stringify(data) }),
    delete: (id: string) => request<void>(`/hooks/${id}`, { method: "DELETE" }),
  },
  settings: {
    getWorld: (novelId: string) => request<any>(`/settings/novel/${novelId}/world`),
    updateWorld: (novelId: string, data: any) =>
      request<any>(`/settings/novel/${novelId}/world`, { method: "PUT", body: JSON.stringify(data) }),
    getStyle: (novelId: string) => request<any>(`/settings/novel/${novelId}/style`),
    updateStyle: (novelId: string, data: any) =>
      request<any>(`/settings/novel/${novelId}/style`, { method: "PUT", body: JSON.stringify(data) }),
  },
};
