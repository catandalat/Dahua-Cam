import { useEffect, useState } from "react";
import { api, Session } from "../api";

function fmtSpeed(v?: number | null) {
  return v != null && !Number.isNaN(Number(v)) ? `${v} km/h` : "—";
}

export default function HistoryPage() {
  const [rows, setRows] = useState<Session[]>([]);
  const [plate, setPlate] = useState("");

  const load = () => {
    const q = new URLSearchParams({ limit: "100", status: "completed" });
    if (plate.trim()) q.set("plate", plate.trim());
    api.sessions(`?${q}`).then(setRows).catch(console.error);
  };

  useEffect(() => {
    load();
  }, []);

  return (
    <div className="space-y-4 md:space-y-6">
      <header className="space-y-3">
        <div>
          <h2 className="text-xl md:text-2xl font-semibold">Lịch sử ra / vào</h2>
          <p className="text-slate-400 text-sm mt-1">
            Các phiên đã hoàn tất · kèm tốc độ lúc vào / ra
          </p>
        </div>
        <div className="flex flex-col sm:flex-row gap-2">
          <input
            value={plate}
            onChange={(e) => setPlate(e.target.value)}
            placeholder="Lọc biển số"
            className="flex-1 bg-ink border border-line rounded-lg px-3 py-2.5 text-sm"
          />
          <button
            type="button"
            onClick={load}
            className="bg-accent/20 text-accent border border-accent/30 rounded-lg px-3 py-2.5 text-sm"
          >
            Lọc
          </button>
          <a
            href={api.exportSessionsUrl(7)}
            className="border border-line rounded-lg px-3 py-2.5 text-sm text-slate-300 hover:bg-white/5 text-center"
          >
            Xuất CSV
          </a>
        </div>
      </header>

      <div className="md:hidden space-y-2">
        {rows.map((r) => (
          <div key={r.id} className="rounded-xl border border-line bg-panel/70 p-3 text-sm">
            <div className="font-mono text-lg">{r.plate_number}</div>
            <div className="text-slate-400 mt-1">
              Vào: {r.entered_at ? new Date(r.entered_at).toLocaleString("vi-VN") : "—"}
              <span className="text-accent font-mono ml-2">{fmtSpeed(r.entry_speed)}</span>
            </div>
            <div className="text-slate-400">
              Ra: {r.exited_at ? new Date(r.exited_at).toLocaleString("vi-VN") : "—"}
              <span className="text-accent font-mono ml-2">{fmtSpeed(r.exit_speed)}</span>
            </div>
            <div className="text-slate-300 mt-1">
              Thời gian:{" "}
              {r.duration_sec != null ? `${Math.round(r.duration_sec / 60)} phút` : "—"}
            </div>
            <div className="text-slate-400 mt-0.5">
              {[r.vehicle_brand, r.vehicle_color].filter(Boolean).join(" · ") || "—"}
            </div>
          </div>
        ))}
        {!rows.length && (
          <div className="text-slate-500 text-sm border border-dashed border-line rounded-xl p-6 text-center">
            Chưa có lịch sử
          </div>
        )}
      </div>

      <div className="hidden md:block overflow-auto rounded-xl border border-line">
        <table className="w-full text-sm">
          <thead className="bg-panel text-slate-400 text-left">
            <tr>
              <th className="px-3 py-2">Biển số</th>
              <th className="px-3 py-2">Vào</th>
              <th className="px-3 py-2">Tốc độ vào</th>
              <th className="px-3 py-2">Ra</th>
              <th className="px-3 py-2">Tốc độ ra</th>
              <th className="px-3 py-2">Thời gian</th>
              <th className="px-3 py-2">Xe</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.id} className="border-t border-line/80">
                <td className="px-3 py-2 font-mono">{r.plate_number}</td>
                <td className="px-3 py-2">
                  {r.entered_at ? new Date(r.entered_at).toLocaleString("vi-VN") : "—"}
                </td>
                <td className="px-3 py-2 font-mono text-accent">{fmtSpeed(r.entry_speed)}</td>
                <td className="px-3 py-2">
                  {r.exited_at ? new Date(r.exited_at).toLocaleString("vi-VN") : "—"}
                </td>
                <td className="px-3 py-2 font-mono text-accent">{fmtSpeed(r.exit_speed)}</td>
                <td className="px-3 py-2 font-mono">
                  {r.duration_sec != null ? `${Math.round(r.duration_sec / 60)} phút` : "—"}
                </td>
                <td className="px-3 py-2 text-slate-300">
                  {[r.vehicle_brand, r.vehicle_color].filter(Boolean).join(" · ") || "—"}
                </td>
              </tr>
            ))}
            {!rows.length && (
              <tr>
                <td colSpan={7} className="px-3 py-8 text-center text-slate-500">
                  Chưa có lịch sử
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
