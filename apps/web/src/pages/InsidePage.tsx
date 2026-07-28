import { useEffect, useState } from "react";
import { api, Session } from "../api";

export default function InsidePage() {
  const [rows, setRows] = useState<Session[]>([]);
  const [error, setError] = useState<string | null>(null);

  const load = () =>
    api
      .sessions("?status=inside&limit=200")
      .then(setRows)
      .catch((e) => setError(String(e)));

  useEffect(() => {
    load();
    const t = setInterval(load, 10000);
    return () => clearInterval(t);
  }, []);

  return (
    <div className="space-y-4 md:space-y-6">
      <header className="flex items-end justify-between gap-3 flex-wrap">
        <div>
          <h2 className="text-xl md:text-2xl font-semibold">Xe trong khu vực</h2>
          <p className="text-slate-400 text-sm mt-1">Các phiên đang mở (đã vào, chưa ra)</p>
        </div>
        <button
          type="button"
          onClick={load}
          className="text-sm border border-line rounded-lg px-3 py-2 hover:bg-white/5"
        >
          Làm mới
        </button>
      </header>

      {error && <div className="text-danger text-sm">{error}</div>}

      <div className="md:hidden space-y-2">
        {rows.map((r) => (
          <div key={r.id} className="rounded-xl border border-line bg-panel/70 p-3 text-sm">
            <div className="font-mono text-lg">{r.plate_number}</div>
            <div className="text-slate-400 mt-1">
              Vào: {r.entered_at ? new Date(r.entered_at).toLocaleString("vi-VN") : "—"}
            </div>
            <div className="text-slate-400 mt-0.5">
              {[r.vehicle_brand, r.vehicle_color].filter(Boolean).join(" · ") || "—"}
            </div>
          </div>
        ))}
        {!rows.length && !error && (
          <div className="text-slate-500 text-sm border border-dashed border-line rounded-xl p-6 text-center">
            Không có xe trong khu vực
          </div>
        )}
      </div>

      <div className="hidden md:block overflow-auto rounded-xl border border-line">
        <table className="w-full text-sm">
          <thead className="bg-panel text-slate-400 text-left">
            <tr>
              <th className="px-3 py-2 font-medium">Biển số</th>
              <th className="px-3 py-2 font-medium">Vào lúc</th>
              <th className="px-3 py-2 font-medium">Xe</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.id} className="border-t border-line/80">
                <td className="px-3 py-2 font-mono">{r.plate_number}</td>
                <td className="px-3 py-2">
                  {r.entered_at ? new Date(r.entered_at).toLocaleString("vi-VN") : "—"}
                </td>
                <td className="px-3 py-2 text-slate-300">
                  {[r.vehicle_brand, r.vehicle_color].filter(Boolean).join(" · ") || "—"}
                </td>
              </tr>
            ))}
            {!rows.length && (
              <tr>
                <td colSpan={3} className="px-3 py-8 text-center text-slate-500">
                  Không có xe trong khu vực
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
