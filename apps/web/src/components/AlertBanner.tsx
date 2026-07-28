import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, WatchAlert, WS_URL } from "../api";

type Toast = { kind: "watch"; data: WatchAlert };

export default function AlertBanner({ onNavigate }: { onNavigate?: () => void }) {
  const [unread, setUnread] = useState(0);
  const [toast, setToast] = useState<Toast | null>(null);

  useEffect(() => {
    api.watchUnreadCount().then((r) => setUnread(r.count)).catch(() => null);

    if (typeof Notification !== "undefined" && Notification.permission === "default") {
      Notification.requestPermission().catch(() => null);
    }

    const ws = new WebSocket(WS_URL);
    ws.onmessage = (ev) => {
      try {
        const msg = JSON.parse(ev.data);
        if (msg.type === "watch_alert" && msg.alert) {
          const alert = msg.alert as WatchAlert;
          setToast({ kind: "watch", data: alert });
          setUnread((n) => n + 1);
          if (typeof Notification !== "undefined" && Notification.permission === "granted") {
            new Notification(`Truy vết ${alert.plate_number}`, {
              body: alert.message,
              tag: alert.id,
            });
          }
          setTimeout(() => setToast((t) => (t?.kind === "watch" && t.data.id === alert.id ? null : t)), 12000);
        }
      } catch {
        /* ignore */
      }
    };
    const ping = setInterval(() => {
      if (ws.readyState === WebSocket.OPEN) ws.send("ping");
    }, 20000);
    const poll = setInterval(() => {
      api.watchUnreadCount().then((r) => setUnread(r.count)).catch(() => null);
    }, 30000);
    return () => {
      clearInterval(ping);
      clearInterval(poll);
      ws.close();
    };
  }, []);

  return (
    <>
      <Link
        to="/watch"
        onClick={onNavigate}
        className={`rounded-lg px-3 py-2.5 text-sm transition flex items-center justify-between gap-2 ${
          unread > 0 ? "bg-danger/15 text-danger" : "text-slate-300 hover:bg-white/5"
        }`}
      >
        <span>Truy vết biển số</span>
        {unread > 0 && (
          <span className="font-mono text-xs bg-danger text-white rounded-full min-w-5 h-5 px-1.5 flex items-center justify-center">
            {unread > 99 ? "99+" : unread}
          </span>
        )}
      </Link>

      {toast?.kind === "watch" && (
        <div className="fixed top-3 left-3 right-3 md:left-auto md:right-4 md:w-96 z-[60] border border-danger/50 bg-panel shadow-xl rounded-xl p-4">
          <div className="flex items-start justify-between gap-2">
            <div className="min-w-0">
              <div className="text-xs uppercase tracking-wide text-danger">Cảnh báo truy vết</div>
              <div className="font-mono text-xl mt-1">{toast.data.plate_number}</div>
              <p className="text-sm text-slate-300 mt-2 break-words">{toast.data.message}</p>
            </div>
            <button type="button" className="text-slate-500 text-sm shrink-0 p-1" onClick={() => setToast(null)}>
              ✕
            </button>
          </div>
          <div className="mt-3 flex flex-wrap gap-2">
            <Link
              to="/watch"
              className="text-xs border border-danger/40 text-danger rounded-lg px-3 py-1.5"
              onClick={() => {
                setToast(null);
                onNavigate?.();
              }}
            >
              Xem chi tiết
            </Link>
            <button
              type="button"
              className="text-xs border border-line rounded-lg px-3 py-1.5"
              onClick={async () => {
                await api.markAlertRead(toast.data.id);
                setUnread((n) => Math.max(0, n - 1));
                setToast(null);
              }}
            >
              Đã đọc
            </button>
          </div>
        </div>
      )}
    </>
  );
}
