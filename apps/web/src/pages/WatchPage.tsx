import { FormEvent, useEffect, useState } from "react";
import { api, PlateWatch, Site, WatchAlert } from "../api";

const PRIORITY_LABEL: Record<string, string> = {
  low: "Thấp",
  normal: "Thường",
  high: "Cao",
  critical: "Khẩn cấp",
};

export default function WatchPage() {
  const [watches, setWatches] = useState<PlateWatch[]>([]);
  const [alerts, setAlerts] = useState<WatchAlert[]>([]);
  const [sites, setSites] = useState<Site[]>([]);
  const [msg, setMsg] = useState<string | null>(null);
  const [form, setForm] = useState({
    plate_number: "",
    label: "",
    note: "",
    priority: "high",
    site_id: "",
  });

  const refresh = async () => {
    const [w, a, s] = await Promise.all([
      api.watches(),
      api.watchAlerts("?limit=100"),
      api.sites(),
    ]);
    setWatches(w);
    setAlerts(a);
    setSites(s);
  };

  useEffect(() => {
    refresh().catch(console.error);
    const t = setInterval(() => refresh().catch(() => null), 10000);
    return () => clearInterval(t);
  }, []);

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setMsg(null);
    try {
      await api.createWatch({
        plate_number: form.plate_number,
        label: form.label || null,
        note: form.note || null,
        priority: form.priority,
        site_id: form.site_id || null,
        active: true,
        notify_dashboard: true,
      });
      setForm((f) => ({ ...f, plate_number: "", label: "", note: "" }));
      setMsg("Đã thêm biển số vào danh sách truy vết");
      await refresh();
    } catch (err) {
      setMsg(String(err));
    }
  };

  return (
    <div className="space-y-4 md:space-y-6">
      <header>
        <h2 className="text-xl md:text-2xl font-semibold">Truy vết biển số</h2>
        <p className="text-slate-400 text-sm mt-1">
          Nhập biển cần theo dõi — khi camera nhận diện, quản trị viên nhận thông báo ngay
        </p>
      </header>

      {msg && <div className="text-sm border border-line rounded-lg px-3 py-2 break-words">{msg}</div>}

      <form
        onSubmit={onSubmit}
        className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-3 border border-line rounded-xl bg-panel/60 p-3 md:p-4"
      >
        <label className="text-sm space-y-1 block">
          <span className="text-slate-400">Biển số *</span>
          <input
            className="w-full bg-ink border border-line rounded-lg px-3 py-2.5 font-mono"
            value={form.plate_number}
            onChange={(e) => setForm({ ...form, plate_number: e.target.value })}
            placeholder="30A12345"
            required
          />
        </label>
        <label className="text-sm space-y-1 block">
          <span className="text-slate-400">Nhãn / lý do</span>
          <input
            className="w-full bg-ink border border-line rounded-lg px-3 py-2.5"
            value={form.label}
            onChange={(e) => setForm({ ...form, label: e.target.value })}
            placeholder="Xe cần tìm"
          />
        </label>
        <label className="text-sm space-y-1 block">
          <span className="text-slate-400">Mức ưu tiên</span>
          <select
            className="w-full bg-ink border border-line rounded-lg px-3 py-2.5"
            value={form.priority}
            onChange={(e) => setForm({ ...form, priority: e.target.value })}
          >
            <option value="low">Thấp</option>
            <option value="normal">Thường</option>
            <option value="high">Cao</option>
            <option value="critical">Khẩn cấp</option>
          </select>
        </label>
        <label className="text-sm space-y-1 block">
          <span className="text-slate-400">Phạm vi khu vực</span>
          <select
            className="w-full bg-ink border border-line rounded-lg px-3 py-2.5"
            value={form.site_id}
            onChange={(e) => setForm({ ...form, site_id: e.target.value })}
          >
            <option value="">Tất cả khu vực</option>
            {sites.map((s) => (
              <option key={s.id} value={s.id}>
                {s.name}
              </option>
            ))}
          </select>
        </label>
        <div className="flex items-end">
          <button
            type="submit"
            className="w-full bg-danger/20 text-danger border border-danger/30 rounded-lg px-4 py-2.5 text-sm"
          >
            Theo dõi
          </button>
        </div>
      </form>

      <section>
        <h3 className="text-sm text-slate-400 mb-2">Đang theo dõi</h3>
        <div className="md:hidden space-y-2">
          {watches.map((w) => (
            <div key={w.id} className="rounded-xl border border-line bg-panel/70 p-3 text-sm">
              <div className="font-mono text-lg">{w.plate_number}</div>
              <div className="text-slate-400 mt-1">
                {w.label || "—"} · {PRIORITY_LABEL[w.priority] || w.priority} ·{" "}
                {w.active ? "Đang bật" : "Tạm dừng"}
              </div>
              <div className="mt-2 flex gap-3">
                <button
                  type="button"
                  className="text-xs text-slate-300"
                  onClick={async () => {
                    await api.updateWatch(w.id, { active: !w.active });
                    await refresh();
                  }}
                >
                  {w.active ? "Tạm dừng" : "Bật lại"}
                </button>
                <button
                  type="button"
                  className="text-xs text-danger"
                  onClick={async () => {
                    await api.deleteWatch(w.id);
                    await refresh();
                  }}
                >
                  Xoá
                </button>
              </div>
            </div>
          ))}
          {!watches.length && (
            <div className="text-slate-500 text-sm border border-dashed border-line rounded-xl p-6 text-center">
              Chưa có biển số nào được theo dõi
            </div>
          )}
        </div>

        <div className="hidden md:block overflow-auto rounded-xl border border-line">
          <table className="w-full text-sm">
            <thead className="bg-panel text-slate-400 text-left">
              <tr>
                <th className="px-3 py-2">Biển số</th>
                <th className="px-3 py-2">Nhãn</th>
                <th className="px-3 py-2">Ưu tiên</th>
                <th className="px-3 py-2">Trạng thái</th>
                <th className="px-3 py-2"></th>
              </tr>
            </thead>
            <tbody>
              {watches.map((w) => (
                <tr key={w.id} className="border-t border-line/80">
                  <td className="px-3 py-2 font-mono text-base">{w.plate_number}</td>
                  <td className="px-3 py-2">{w.label || "—"}</td>
                  <td className="px-3 py-2">
                    <PriorityBadge priority={w.priority} />
                  </td>
                  <td className="px-3 py-2">{w.active ? "Đang bật" : "Tạm dừng"}</td>
                  <td className="px-3 py-2 text-right space-x-2">
                    <button
                      type="button"
                      className="text-xs text-slate-300"
                      onClick={async () => {
                        await api.updateWatch(w.id, { active: !w.active });
                        await refresh();
                      }}
                    >
                      {w.active ? "Tạm dừng" : "Bật lại"}
                    </button>
                    <button
                      type="button"
                      className="text-xs text-danger"
                      onClick={async () => {
                        await api.deleteWatch(w.id);
                        await refresh();
                      }}
                    >
                      Xoá
                    </button>
                  </td>
                </tr>
              ))}
              {!watches.length && (
                <tr>
                  <td colSpan={5} className="px-3 py-8 text-center text-slate-500">
                    Chưa có biển số nào được theo dõi
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </section>

      <section>
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 mb-2">
          <h3 className="text-sm text-slate-400">Lịch sử cảnh báo</h3>
          <button
            type="button"
            className="text-xs border border-line rounded-lg px-2.5 py-1.5 hover:bg-white/5 self-start"
            onClick={async () => {
              await api.markAllAlertsRead();
              await refresh();
            }}
          >
            Đánh dấu đã đọc hết
          </button>
        </div>
        <div className="space-y-2">
          {alerts.map((a) => (
            <article
              key={a.id}
              className={`rounded-xl border p-3 flex flex-col sm:flex-row gap-3 items-start ${
                a.read ? "border-line bg-panel/40" : "border-danger/40 bg-danger/10"
              }`}
            >
              {a.detection_id && a.image_paths ? (
                <img
                  src={api.mediaUrl(
                    a.detection_id,
                    a.image_paths.plate
                      ? "plate"
                      : a.image_paths.vehicle
                        ? "vehicle"
                        : Object.keys(a.image_paths)[0],
                  )}
                  alt=""
                  className="w-full sm:w-24 h-32 sm:h-16 object-cover rounded-lg border border-line bg-ink"
                />
              ) : (
                <div className="w-full sm:w-24 h-20 sm:h-16 rounded-lg border border-line bg-ink" />
              )}
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="font-mono text-lg">{a.plate_number}</span>
                  <PriorityBadge priority={a.priority} />
                  {!a.read && (
                    <span className="text-[11px] uppercase text-danger">Mới</span>
                  )}
                </div>
                <p className="text-sm text-slate-300 mt-1 break-words">{a.message}</p>
                <div className="text-xs text-slate-500 mt-1 font-mono">
                  {a.event_utc ? new Date(a.event_utc).toLocaleString("vi-VN") : "—"}
                </div>
              </div>
              {!a.read && (
                <button
                  type="button"
                  className="text-xs border border-line rounded-lg px-2.5 py-1.5 shrink-0"
                  onClick={async () => {
                    await api.markAlertRead(a.id);
                    await refresh();
                  }}
                >
                  Đã đọc
                </button>
              )}
            </article>
          ))}
          {!alerts.length && (
            <div className="text-slate-500 text-sm border border-dashed border-line rounded-xl p-6 text-center">
              Chưa có cảnh báo truy vết
            </div>
          )}
        </div>
      </section>
    </div>
  );
}

function PriorityBadge({ priority }: { priority: string }) {
  const color =
    priority === "critical"
      ? "border-danger/50 text-danger bg-danger/10"
      : priority === "high"
        ? "border-warn/50 text-warn bg-warn/10"
        : "border-line text-slate-300";
  return (
    <span className={`text-[11px] uppercase tracking-wide px-2 py-0.5 rounded border ${color}`}>
      {PRIORITY_LABEL[priority] || priority}
    </span>
  );
}
