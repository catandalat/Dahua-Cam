import { FormEvent, useEffect, useState } from "react";
import { api, Camera, PlateList, Site } from "../api";

export default function PlatesPage() {
  const [rows, setRows] = useState<PlateList[]>([]);
  const [sites, setSites] = useState<Site[]>([]);
  const [cameras, setCameras] = useState<Camera[]>([]);
  const [form, setForm] = useState({
    site_id: "",
    list_type: "allow",
    plate_number: "",
    note: "",
  });
  const [msg, setMsg] = useState<string | null>(null);

  const refresh = async () => {
    const [p, s, c] = await Promise.all([api.plateLists(), api.sites(), api.cameras()]);
    setRows(p);
    setSites(s);
    setCameras(c);
    if (!form.site_id && s[0]) setForm((f) => ({ ...f, site_id: s[0].id }));
  };

  useEffect(() => {
    refresh().catch(console.error);
  }, []);

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault();
    await api.createPlate(form);
    setForm((f) => ({ ...f, plate_number: "", note: "" }));
    await refresh();
  };

  const sync = async (cameraId: string) => {
    try {
      const res = await api.syncPlates(cameraId);
      setMsg(
        `Đã đồng bộ ${res.synced}` +
          (res.errors.length ? ` · lỗi: ${res.errors.join("; ")}` : ""),
      );
      await refresh();
    } catch (err) {
      setMsg(String(err));
    }
  };

  return (
    <div className="space-y-4 md:space-y-6">
      <header>
        <h2 className="text-xl md:text-2xl font-semibold">Danh sách biển</h2>
        <p className="text-slate-400 text-sm mt-1">
          Danh sách trắng / đen trên hệ thống · đồng bộ xuống camera (tuỳ chọn)
        </p>
      </header>

      {msg && <div className="text-sm border border-line rounded-lg px-3 py-2 break-words">{msg}</div>}

      <form
        onSubmit={onSubmit}
        className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3 border border-line rounded-xl bg-panel/60 p-3 md:p-4"
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
          <span className="text-slate-400">Loại</span>
          <select
            className="w-full bg-ink border border-line rounded-lg px-3 py-2.5"
            value={form.list_type}
            onChange={(e) => setForm({ ...form, list_type: e.target.value })}
          >
            <option value="allow">Danh sách trắng</option>
            <option value="block">Danh sách đen</option>
          </select>
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
        <div className="flex items-end">
          <button
            type="submit"
            className="w-full bg-accent/20 text-accent border border-accent/30 rounded-lg px-4 py-2.5 text-sm"
          >
            Thêm
          </button>
        </div>
      </form>

      {cameras.length > 0 && (
        <div className="flex flex-wrap gap-2">
          <span className="text-sm text-slate-400 self-center">Đồng bộ xuống camera:</span>
          {cameras.map((c) => (
            <button
              key={c.id}
              type="button"
              onClick={() => sync(c.id)}
              className="text-xs border border-line rounded-lg px-2.5 py-1.5 hover:bg-white/5"
            >
              {c.name}
            </button>
          ))}
        </div>
      )}

      <div className="md:hidden space-y-2">
        {rows.map((r) => (
          <div key={r.id} className="rounded-xl border border-line bg-panel/70 p-3 text-sm">
            <div className="font-mono text-lg">{r.plate_number}</div>
            <div className="text-slate-400 mt-1">
              {r.list_type === "allow" ? "Danh sách trắng" : "Danh sách đen"} ·{" "}
              {r.synced_to_camera ? "Đã đồng bộ" : "Chưa đồng bộ"}
            </div>
            <button
              type="button"
              className="text-danger text-xs mt-2"
              onClick={async () => {
                await api.deletePlate(r.id);
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
              <th className="px-3 py-2">Loại</th>
              <th className="px-3 py-2">Đồng bộ</th>
              <th className="px-3 py-2"></th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.id} className="border-t border-line/80">
                <td className="px-3 py-2 font-mono">{r.plate_number}</td>
                <td className="px-3 py-2">
                  {r.list_type === "allow" ? "Danh sách trắng" : "Danh sách đen"}
                </td>
                <td className="px-3 py-2">{r.synced_to_camera ? "Có" : "Chưa"}</td>
                <td className="px-3 py-2 text-right">
                  <button
                    type="button"
                    className="text-danger text-xs"
                    onClick={async () => {
                      await api.deletePlate(r.id);
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
                <td colSpan={4} className="px-3 py-8 text-center text-slate-500">
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
