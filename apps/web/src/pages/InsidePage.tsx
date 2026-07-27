import { useEffect, useState } from "react";
import { api, Session } from "../api";

function fmtSpeed(v?: number | null) {
  return v != null && !Number.isNaN(Number(v)) ? `${v} km/h` : "—";
}

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
      <header>
        <h2 className="text-xl md:text-2xl font-semibold">Xe đang trong khu vực</h2>
        <p className="text-slate-400 text-sm mt-1">Đã vào nhưng chưa ra · tốc độ lúc ghi nhận vào</p>
      </header>
      {error && <div className="text-danger text-sm">{error}</div>}
      <Table rows={rows} />
    </div>
  );
}

export function Table({ rows }: { rows: Session[] }) {
  return (
    <>
      <div className="md:hidden space-y-2">
        {rows.map((r) => (
          <div key={r.id} className="rounded-xl border border-line bg-panel/70 p-3">
            <div className="font-mono text-lg">{r.plate_number}</div>
            <div className="text-sm text-slate-400 mt-1">
              Vào: {r.entered_at ? new Date(r.entered_at).toLocaleString("vi-VN") : "—"}
            </div>
            <div className="text-sm text-accent font-mono mt-0.5">
              Tốc độ vào: {fmtSpeed(r.entry_speed)}
            </div>
            <div className="text-sm text-slate-400">
              {[r.vehicle_brand, r.vehicle_color].filter(Boolean).join(" · ") || "—"}
            </div>
            <div className="mt-2 text-sm">
              {r.overstay ? (
                <span className="text-warn">Quá thời gian lưu trú</span>
              ) : (
                <span className="text-ok">Đang trong khu vực</span>
              )}
            </div>
          </div>
        ))}
        {!rows.length && (
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
              <th className="px-3 py-2 font-medium">Tốc độ vào</th>
              <th className="px-3 py-2 font-medium">Xe</th>
              <th className="px-3 py-2 font-medium">Trạng thái</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.id} className="border-t border-line/80">
                <td className="px-3 py-2 font-mono">{r.plate_number}</td>
                <td className="px-3 py-2 text-slate-300">
                  {r.entered_at ? new Date(r.entered_at).toLocaleString("vi-VN") : "—"}
                </td>
                <td className="px-3 py-2 font-mono text-accent">{fmtSpeed(r.entry_speed)}</td>
                <td className="px-3 py-2 text-slate-300">
                  {[r.vehicle_brand, r.vehicle_color].filter(Boolean).join(" · ") || "—"}
                </td>
                <td className="px-3 py-2">
                  {r.overstay ? (
                    <span className="text-warn">Quá thời gian lưu trú</span>
                  ) : (
                    <span className="text-ok">Đang trong khu vực</span>
                  )}
                </td>
              </tr>
            ))}
            {!rows.length && (
              <tr>
                <td colSpan={5} className="px-3 py-8 text-center text-slate-500">
                  Không có xe trong khu vực
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </>
  );
}
