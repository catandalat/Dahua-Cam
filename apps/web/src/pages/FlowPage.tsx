import { useEffect, useState } from "react";
import { api, Camera, FlowByLane, FlowSample, JamEvent } from "../api";

export default function FlowPage() {
  const [byLane, setByLane] = useState<FlowByLane[]>([]);
  const [samples, setSamples] = useState<FlowSample[]>([]);
  const [jams, setJams] = useState<JamEvent[]>([]);
  const [cameras, setCameras] = useState<Camera[]>([]);
  const [msg, setMsg] = useState<string | null>(null);

  const load = () => {
    api.flowByLane("?hours=24").then(setByLane).catch(console.error);
    api.flow("?limit=50").then(setSamples).catch(console.error);
    api.jams("?limit=30").then(setJams).catch(console.error);
    api.cameras().then(setCameras).catch(console.error);
  };

  useEffect(() => {
    load();
    const t = setInterval(load, 15000);
    return () => clearInterval(t);
  }, []);

  return (
    <div className="space-y-4 md:space-y-6">
      <header className="space-y-3">
        <div>
          <h2 className="text-xl md:text-2xl font-semibold">Lưu lượng & kẹt xe</h2>
          <p className="text-slate-400 text-sm mt-1">
            Thống kê lưu lượng theo làn · phân bố phương tiện · cảnh báo kẹt
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          {cameras.map((c) => (
            <button
              key={c.id}
              type="button"
              className="text-xs border border-line rounded-lg px-2.5 py-1.5 hover:bg-white/5"
              onClick={async () => {
                try {
                  const r = await api.pullFlowHistory(c.id, 2);
                  setMsg(`Đã kéo lịch sử từ ${c.name}`);
                  void r;
                  load();
                } catch (e) {
                  setMsg(String(e));
                }
              }}
            >
              Kéo lịch sử · {c.name}
            </button>
          ))}
        </div>
      </header>

      {msg && <div className="text-sm border border-line rounded-lg px-3 py-2 text-slate-300 break-words">{msg}</div>}

      <section>
        <h3 className="text-sm text-slate-400 mb-2">Tổng 24 giờ theo làn</h3>
        <div className="overflow-x-auto rounded-xl border border-line">
          <table className="w-full text-sm min-w-[320px]">
            <thead className="bg-panel text-slate-400 text-left">
              <tr>
                <th className="px-3 py-2">Làn</th>
                <th className="px-3 py-2">Hướng</th>
                <th className="px-3 py-2">Tổng xe</th>
                <th className="px-3 py-2">Mẫu</th>
              </tr>
            </thead>
            <tbody>
              {byLane.map((r, i) => (
                <tr key={i} className="border-t border-line/80">
                  <td className="px-3 py-2 font-mono">{r.lane_number ?? "—"}</td>
                  <td className="px-3 py-2">{r.direction ?? "—"}</td>
                  <td className="px-3 py-2 font-mono">{r.vehicles_sum}</td>
                  <td className="px-3 py-2 font-mono">{r.samples}</td>
                </tr>
              ))}
              {!byLane.length && (
                <tr>
                  <td colSpan={4} className="px-3 py-6 text-center text-slate-500">
                    Chưa có mẫu lưu lượng
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </section>

      <section className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div>
          <h3 className="text-sm text-slate-400 mb-2">Mẫu gần đây</h3>
          <div className="space-y-2 max-h-80 overflow-auto">
            {samples.map((s) => (
              <div key={s.id} className="border border-line rounded-lg px-3 py-2 text-sm bg-panel/50">
                <div className="font-mono">
                  Làn {s.lane_number ?? "—"} · số xe={s.vehicles_num ?? "—"} · hàng đợi=
                  {s.queue_len ?? "—"}
                </div>
                <div className="text-xs text-slate-500">
                  {s.direction || s.event_code} ·{" "}
                  {s.event_utc ? new Date(s.event_utc).toLocaleString("vi-VN") : "—"}
                </div>
              </div>
            ))}
          </div>
        </div>
        <div>
          <h3 className="text-sm text-slate-400 mb-2">Cảnh báo kẹt xe</h3>
          <div className="space-y-2 max-h-80 overflow-auto">
            {jams.map((j) => (
              <div key={j.id} className="border border-warn/30 bg-warn/5 rounded-lg px-3 py-2 text-sm">
                <div>
                  Làn {j.lane_number ?? "—"} · {j.jam_length_pct ?? "—"}% · {j.jam_real_length_m ?? "—"} m
                </div>
                <div className="text-xs text-slate-500">
                  {j.event_utc ? new Date(j.event_utc).toLocaleString("vi-VN") : "—"}
                </div>
              </div>
            ))}
            {!jams.length && <div className="text-slate-500 text-sm">Không có cảnh báo kẹt xe</div>}
          </div>
        </div>
      </section>
    </div>
  );
}
