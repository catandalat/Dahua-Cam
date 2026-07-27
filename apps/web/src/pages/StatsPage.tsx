import { useEffect, useMemo, useState } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { api, SessionStats, VehicleStats } from "../api";

const CLASS_LABEL: Record<string, string> = {
  car: "Ô tô",
  motorcycle: "Xe máy",
  other: "Khác",
  unknown: "Chưa rõ",
};

export default function StatsPage() {
  const [stats, setStats] = useState<SessionStats | null>(null);
  const [vstats, setVstats] = useState<VehicleStats | null>(null);

  useEffect(() => {
    api.sessionStats("?days=7").then(setStats).catch(console.error);
    api.vehicleStats("?days=7").then(setVstats).catch(console.error);
    const t = setInterval(() => {
      api.sessionStats("?days=7").then(setStats).catch(() => null);
      api.vehicleStats("?days=7").then(setVstats).catch(() => null);
    }, 15000);
    return () => clearInterval(t);
  }, []);

  const chartData = useMemo(() => {
    if (!stats) return [];
    const map = new Map<string, { hour: string; entry: number; exit: number }>();
    for (const row of stats.hourly) {
      const key = row.hour ? new Date(row.hour).toLocaleString("vi-VN") : "—";
      const cur = map.get(key) || { hour: key, entry: 0, exit: 0 };
      if (row.direction === "entry") cur.entry += row.count;
      else if (row.direction === "exit") cur.exit += row.count;
      else cur.entry += row.count;
      map.set(key, cur);
    }
    return Array.from(map.values());
  }, [stats]);

  return (
    <div className="space-y-4 md:space-y-6">
      <header className="flex flex-col sm:flex-row sm:items-end justify-between gap-3">
        <div>
          <h2 className="text-xl md:text-2xl font-semibold">Thống kê ra / vào</h2>
          <p className="text-slate-400 text-sm mt-1">7 ngày gần nhất · loại xe / màu / hãng</p>
        </div>
        <a
          href={api.exportDetectionsUrl(1)}
          className="border border-line rounded-lg px-3 py-2.5 text-sm text-slate-300 hover:bg-white/5 text-center"
        >
          Xuất nhận diện CSV
        </a>
      </header>

      {stats && (
        <div className="grid grid-cols-3 gap-2 md:gap-3">
          {[
            ["Lượt vào", stats.entries],
            ["Lượt ra", stats.exits],
            ["Trong khu vực", stats.inside],
          ].map(([label, value]) => (
            <div key={String(label)} className="rounded-xl border border-line bg-panel px-3 py-3">
              <div className="text-xs text-slate-500">{label}</div>
              <div className="text-xl md:text-2xl font-semibold mt-1 font-mono">{value}</div>
            </div>
          ))}
        </div>
      )}

      <div className="h-64 md:h-80 rounded-xl border border-line bg-panel/60 p-2 md:p-4">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={chartData}>
            <CartesianGrid stroke="#243041" strokeDasharray="3 3" />
            <XAxis dataKey="hour" tick={{ fill: "#94a3b8", fontSize: 10 }} hide={chartData.length > 8} />
            <YAxis tick={{ fill: "#94a3b8", fontSize: 11 }} width={32} />
            <Tooltip contentStyle={{ background: "#161d27", border: "1px solid #243041" }} />
            <Legend />
            <Bar dataKey="entry" name="Vào" fill="#3ecf8e" />
            <Bar dataKey="exit" name="Ra" fill="#3d9cf0" />
          </BarChart>
        </ResponsiveContainer>
      </div>

      {vstats && (
        <div className="grid grid-cols-1 md:grid-cols-3 gap-3 md:gap-4">
          <Breakdown
            title="Theo loại xe"
            rows={vstats.by_class.map((r) => ({
              key: CLASS_LABEL[r.key] || r.key,
              count: r.count,
            }))}
          />
          <Breakdown title="Theo màu xe" rows={vstats.by_color} />
          <Breakdown title="Theo hãng xe" rows={vstats.by_brand} />
        </div>
      )}
    </div>
  );
}

function Breakdown({
  title,
  rows,
}: {
  title: string;
  rows: { key: string; count: number }[];
}) {
  return (
    <div className="rounded-xl border border-line bg-panel/60 overflow-hidden">
      <div className="px-3 py-2 text-sm text-slate-400 border-b border-line">{title}</div>
      <table className="w-full text-sm">
        <tbody>
          {rows.slice(0, 12).map((r) => (
            <tr key={String(r.key)} className="border-t border-line/60">
              <td className="px-3 py-1.5 break-all">{r.key}</td>
              <td className="px-3 py-1.5 text-right font-mono">{r.count}</td>
            </tr>
          ))}
          {!rows.length && (
            <tr>
              <td className="px-3 py-6 text-center text-slate-500" colSpan={2}>
                Chưa có dữ liệu
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  );
}
