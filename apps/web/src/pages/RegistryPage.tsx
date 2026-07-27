import { FormEvent, useEffect, useState } from "react";
import { api, Camera, RegistryEntry, Site } from "../api";

export default function RegistryPage() {
  const [rows, setRows] = useState<RegistryEntry[]>([]);
  const [sites, setSites] = useState<Site[]>([]);
  const [cameras, setCameras] = useState<Camera[]>([]);
  const [msg, setMsg] = useState<string | null>(null);
  const [form, setForm] = useState({
    site_id: "",
    group_name: "mac-dinh",
    plate_number: "",
    brand: "",
    color: "",
  });

  const refresh = async () => {
    const [r, s, c] = await Promise.all([api.registry(), api.sites(), api.cameras()]);
    setRows(r);
    setSites(s);
    setCameras(c);
    if (!form.site_id && s[0]) setForm((f) => ({ ...f, site_id: s[0].id }));
  };

  useEffect(() => {
    refresh().catch(console.error);
  }, []);

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault();
    await api.createRegistry(form);
    setForm((f) => ({ ...f, plate_number: "", brand: "", color: "" }));
    await refresh();
  };

  return (
    <div className="space-y-4 md:space-y-6">
      <header>
        <h2 className="text-xl md:text-2xl font-semibold">Đăng ký xe</h2>
        <p className="text-slate-400 text-sm mt-1">
          Nhóm phương tiện đăng ký sẵn · đồng bộ xuống camera (nếu hỗ trợ)
        </p>
      </header>

      {msg && <div className="text-sm border border-line rounded-lg px-3 py-2 break-words">{msg}</div>}

      <form
        onSubmit={onSubmit}
        className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-3 border border-line rounded-xl bg-panel/60 p-3 md:p-4"
      >
        <label className="text-sm space-y-1 block">
          <span className="text-slate-400">Khu vực</span>
          <select
            className="w-full bg-ink border border-line rounded-lg px-3 py-2.5"
            value={form.site_id}
            onChange={(e) => setForm({ ...form, site_id: e.target.value })}
          >
            {sites.map((s) => (
              <option key={s.id} value={s.id}>
                {s.name}
              </option>
            ))}
          </select>
        </label>
        <label className="text-sm space-y-1 block">
          <span className="text-slate-400">Nhóm</span>
          <input
            className="w-full bg-ink border border-line rounded-lg px-3 py-2.5"
            value={form.group_name}
            onChange={(e) => setForm({ ...form, group_name: e.target.value })}
          />
        </label>
        <label className="text-sm space-y-1 block">
          <span className="text-slate-400">Biển số</span>
          <input
            className="w-full bg-ink border border-line rounded-lg px-3 py-2.5 font-mono"
            value={form.plate_number}
            onChange={(e) => setForm({ ...form, plate_number: e.target.value })}
            required
          />
        </label>
        <label className="text-sm space-y-1 block">
          <span className="text-slate-400">Hãng</span>
          <input
            className="w-full bg-ink border border-line rounded-lg px-3 py-2.5"
            value={form.brand}
            onChange={(e) => setForm({ ...form, brand: e.target.value })}
          />
        </label>
        <div className="flex items-end">
          <button
            type="submit"
            className="w-full bg-accent/20 text-accent border border-accent/30 rounded-lg px-4 py-2.5 text-sm"
          >
            Thêm
          </button>
        </div>
      </form>

      <div className="flex flex-wrap gap-2">
        <span className="text-sm text-slate-400 self-center">Đồng bộ quản lý xe:</span>
        {cameras.map((c) => (
          <button
            key={c.id}
            type="button"
            className="text-xs border border-line rounded-lg px-2.5 py-1.5 hover:bg-white/5"
            onClick={async () => {
              try {
                const res = await api.syncRegistry(c.id);
                setMsg(
                  `Đã đồng bộ ${res.synced}` +
                    (res.errors.length ? ` · ${res.errors.join("; ")}` : ""),
                );
                await refresh();
              } catch (e) {
                setMsg(String(e));
              }
            }}
          >
            {c.name}
          </button>
        ))}
      </div>

      <div className="md:hidden space-y-2">
        {rows.map((r) => (
          <div key={r.id} className="rounded-xl border border-line bg-panel/70 p-3 text-sm">
            <div className="font-mono text-lg">{r.plate_number}</div>
            <div className="text-slate-400 mt-1">
              Nhóm {r.group_name} · {r.brand || "—"} · {r.synced_to_camera ? "Đã đồng bộ" : "Chưa"}
            </div>
            <button
              type="button"
              className="text-danger text-xs mt-2"
              onClick={async () => {
                await api.deleteRegistry(r.id);
                await refresh();
              }}
            >
              Xoá
            </button>
          </div>
        ))}
        {!rows.length && (
          <div className="text-slate-500 text-sm border border-dashed border-line rounded-xl p-6 text-center">
            Trống
          </div>
        )}
      </div>

      <div className="hidden md:block overflow-auto rounded-xl border border-line">
        <table className="w-full text-sm">
          <thead className="bg-panel text-slate-400 text-left">
            <tr>
              <th className="px-3 py-2">Biển số</th>
              <th className="px-3 py-2">Nhóm</th>
              <th className="px-3 py-2">Hãng</th>
              <th className="px-3 py-2">Đồng bộ</th>
              <th className="px-3 py-2"></th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.id} className="border-t border-line/80">
                <td className="px-3 py-2 font-mono">{r.plate_number}</td>
                <td className="px-3 py-2">{r.group_name}</td>
                <td className="px-3 py-2">{r.brand || "—"}</td>
                <td className="px-3 py-2">{r.synced_to_camera ? "Có" : "Chưa"}</td>
                <td className="px-3 py-2 text-right">
                  <button
                    type="button"
                    className="text-danger text-xs"
                    onClick={async () => {
                      await api.deleteRegistry(r.id);
                      await refresh();
                    }}
                  >
                    Xoá
                  </button>
                </td>
              </tr>
            ))}
            {!rows.length && (
              <tr>
                <td colSpan={5} className="px-3 py-8 text-center text-slate-500">
                  Trống
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
