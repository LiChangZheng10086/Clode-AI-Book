import { useRef, useCallback, useEffect } from "react";

type MessageHandler = (msg: any) => void;

interface WSConnection {
  ws: WebSocket;
  handlers: Set<MessageHandler>;
  pending: any[];
  send: (data: any) => void;
  close: () => void;
}

const connections = new Map<string, WSConnection>();
const closeTimers = new Map<string, ReturnType<typeof setTimeout>>();

const log = (url: string, msg: string, data?: any) => {
  const ts = new Date().toISOString();
  if (data !== undefined) {
    console.log(`[WS ${ts}] ${url} — ${msg}`, data);
  } else {
    console.log(`[WS ${ts}] ${url} — ${msg}`);
  }
};

function getConnection(url: string): WSConnection {
  // Cancel any pending close (e.g. React StrictMode remount)
  const pendingClose = closeTimers.get(url);
  if (pendingClose) {
    log(url, "取消待处理的关闭，复用现有连接");
    clearTimeout(pendingClose);
    closeTimers.delete(url);
  }
  const existing = connections.get(url);
  if (existing) return existing;

  const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
  const fullUrl = `${protocol}//${window.location.host}${url}`;
  log(url, `正在连接 ${fullUrl}`);

  const ws = new WebSocket(fullUrl);
  const handlers = new Set<MessageHandler>();
  const pending: any[] = [];

  const conn: WSConnection = {
    ws,
    handlers,
    pending,
    send: (data: any) => {
      if (ws.readyState === WebSocket.OPEN) {
        const payload = JSON.stringify(data);
        log(url, "发送消息", data);
        ws.send(payload);
      } else if (ws.readyState === WebSocket.CONNECTING) {
        log(url, "WebSocket 未就绪，消息加入队列", data);
        pending.push(data);
      } else {
        console.error(`[WS] ${url} — WebSocket 已关闭，无法发送`, data);
      }
    },
    close: () => {
      // Delay close to survive React StrictMode double-mount / HMR remounts.
      // If a new handler registers within 200ms, the close is cancelled.
      log(url, "延迟关闭连接 (200ms)");
      const timer = setTimeout(() => {
        log(url, "主动关闭连接");
        ws.close();
        connections.delete(url);
        closeTimers.delete(url);
      }, 200);
      closeTimers.set(url, timer);
    },
  };

  ws.onopen = () => {
    log(url, "连接已建立");
    // Flush pending messages
    if (pending.length > 0) {
      log(url, `发送 ${pending.length} 条排队消息`);
      for (const data of pending) {
        ws.send(JSON.stringify(data));
      }
      pending.length = 0;
    }
  };

  ws.onmessage = (event) => {
    const msg = JSON.parse(event.data);
    log(url, "收到消息", msg);
    handlers.forEach((h) => h(msg));
  };

  ws.onerror = (err) => {
    console.error(`[WS] ${url} — 连接错误`, err);
    handlers.forEach((h) => h({ type: "error", message: "WebSocket connection error" }));
  };

  ws.onclose = (event) => {
    log(url, `连接关闭 (code=${event.code})`);
    const timer = closeTimers.get(url);
    if (timer) { clearTimeout(timer); closeTimers.delete(url); }
    connections.delete(url);
    handlers.forEach((h) => h({ type: "connection_closed" }));
  };

  connections.set(url, conn);
  return conn;
}

export function useWS(url: string | null, onMessage: MessageHandler) {
  const onMessageRef = useRef(onMessage);
  onMessageRef.current = onMessage;

  const send = useCallback(
    (data: any) => {
      if (!url) {
        console.warn("[WS] send 被调用但 url 为 null");
        return;
      }
      const conn = getConnection(url);
      conn.send(data);
    },
    [url],
  );

  useEffect(() => {
    if (!url) {
      console.log("[WS] url 为 null，跳过连接");
      return;
    }

    log(url, "组件挂载，注册 handler");
    const conn = getConnection(url);
    const handler: MessageHandler = (msg) => {
      onMessageRef.current(msg);
    };
    conn.handlers.add(handler);

    return () => {
      log(url, "组件卸载，移除 handler");
      conn.handlers.delete(handler);
      if (conn.handlers.size === 0) {
        conn.close();
      }
    };
  }, [url]);

  return { send };
}
