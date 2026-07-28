import { FormEvent, ReactNode, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { api, Camera, PlateList, PlateWatch, RegistryEntry, Site } from "../api";

type Tab = "registry" | "lists";
type ListType = "allow" | "block";

export default function VehiclesPage() {
  const [tab, setTab] = useState<Tab>("registry");
  const [sites, setSites] = useState<Site[]>([]);
  const [cameras, setCameras] = useState<Camera[]>([]);
  const [registry, setRegistry] = useState<RegistryEntry[]>([]);
  const [lists, setLists] = useState<PlateList[]>([]);
  const [watches, setWatches] = useState<PlateWatch[]>([]);
  const [msg, setMsg] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const [siteId, setSiteId] = useState("");
  const [plate, setPlate] = useState("");
  const [groupName, setGroupName] = useState("mac-dinh");
  const [brand, setBrand] = useState("");
  const [color, setColor] = useState("");
  const [listType, setListType] = useState<ListType>("allow");
  const [enableWatch, setEnableWatch] = useState(true);

  const watchByPlate = useMemo(() => {
    const m = new Map<string, PlateWatch>();
    for (const w of watches) {
      if (!w.active) continue;
      m.set(w.plate_number.toUpperCase(), w);
    }
    return m;
  }, [watches]);

  const refresh = async () => {
    const [r, p, s, c, w] = await Promise.all([
      api.registry(),
      api.plateLists(),
      api.sites(),
      api.cameras(),
      api.watches("?active=true"),
    ]);
    setRegistry(r);
    setLists(p);
    setSites(s);
    setCameras(c);
    setWatches(w);
    if (!siteId && s[0]) setSiteId(s[0].id);
  };

  useEffect(() => {
    refresh().catch((e) => setError(String(e)));
  }, []);

  useEffect(() => {
    // Đăng ký: mặc định bật truy vết; danh sách trắng/đen: tắt mặc định
    setEnableWatch(tab === "registry");
  }, [tab]);

  const ensureWatch = async (plateNumber: string, label: string) => {
    if (!enableWatch) return false;
    await api.createWatch({
      plate_number: plateNumber,
      site_id: siteId || null,
      label,
      priority: "normal",
      active: true,
      notify_dashboard: true,
    });
    return true;
  };

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setMsg(null);
    setError(null);
    if (!siteId || !plate.trim()) {
      setError("Chọn khu vực và nhập biển số");
      return;
    }
    try {
      if (tab === "registry") {
        await api.createRegistry({
          site_id: siteId,
          group_name: groupName || "mac-dinh",
          plate_number: plate.trim(),
          brand: brand || undefined,
          color: color || undefined,
        });
        const watched = await ensureWatch(
          plate.trim(),
          brand ? `Đăng ký · ${brand}` : `Đăng ký · ${groupName || "mac-dinh"}`,
        );
        setMsg(
          watched
            ? `Đã đăng ký ${plate.trim().toUpperCase()} và bật truy vết`
            : `Đã đăng ký ${plate.trim().toUpperCase()}`,
        );
        setPlate("");
        setBrand("");
        setColor("");
      } else {
        await api.createPlate({
          site_id: siteId,
          list_type: listType,
          plate_number: plate.trim(),
        });
        const label = listType === "allow" ? "Danh sách trắng" : "Danh sách đen";
        const watched = await ensureWatch(plate.trim(), label);
        setMsg(
          watched
            ? `Đã thêm ${plate.trim().toUpperCase()} vào ${label.toLowerCase()} và bật truy vết`
            : `Đã thêm ${plate.trim().toUpperCase()} vào ${label.toLowerCase()}`,
        );
        setPlate("");
      }
      await refresh();
    } catch (err) {
      setError(String(err));
    }
  };

  return (
    <div className="space-y-4 md:space-y-6">
      <header className="space-y-3">
        <div>
          <h2 className="text-xl md:text-2xl font-semibold">Biển số & xe</h2>
          <p className="text-slate-400 text-sm mt-1">
            Đăng ký xe · danh sách trắng/đen · tùy chọn bật truy vết khi nhận diện
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <TabBtn active={tab === "registry"} onClick={() => setTab("registry")}>
            Đăng ký ({registry.length})
          </TabBtn>
          <TabBtn active={tab === "lists"} onClick={() => setTab("lists")}>
            Cho phép / Chặn ({lists.length})
          </TabBtn>
          <Link
            to="/watch"
            className="text-sm rounded-lg px-3 py-2 border border-danger/40 text-danger hover:bg-danger/10"
          >
            Truy vết đang bật ({watches.length})
          </Link>
        </div>
      </header>

      {(msg || error) && (
        <div
          className={`text-sm border rounded-lg px-3 py-2 break-words ${
            error ? "border-danger/40 text-danger" : "border-line text-slate-300"
          }`}
        >
          {error || msg}
        </div>
      )}

      <form
        onSubmit={onSubmit}
        className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3 border border-line rounded-xl bg-panel/60 p-3 md:p-4"
      >
        <label className="text-sm space-y-1 block">
          <span className="text-slate-400">Khu vực</span>
          <select
            className="w-full bg-ink border border-line rounded-lg px-3 py-2.5"
            value={siteId}
            onChange={(e) => setSiteId(e.target.value)}
            required
          >
            {!sites.length && <option value="">—</option>}
            {sites.map((s) => (
              <option key={s.id} value={s.id}>
                {s.name}
              </option>
            ))}
          </select>
        </label>

        <label className="text-sm space-y-1 block">
          <span className="text-slate-400">Biển số</span>
          <input
            className="w-full bg-ink border border-line rounded-lg px-3 py-2.5 font-mono"
            value={plate}
            onChange={(e) => setPlate(e.target.value)}
            placeholder="51F12345"
            required
          />
        </label>

        {tab === "registry" ? (
          <>
            <label className="text-sm space-y-1 block">
              <span className="text-slate-400">Nhóm</span>
              <input
                className="w-full bg-ink border border-line rounded-lg px-3 py-2.5"
                value={groupName}
                onChange={(e) => setGroupName(e.target.value)}
              />
            </label>
            <label className="text-sm space-y-1 block">
              <span className="text-slate-400">Hãng</span>
              <input
                className="w-full bg-ink border border-line rounded-lg px-3 py-2.5"
                value={brand}
                onChange={(e) => setBrand(e.target.value)}
              />
            </label>
            <label className="text-sm space-y-1 block">
              <span className="text-slate-400">Màu</span>
              <input
                className="w-full bg-ink border border-line rounded-lg px-3 py-2.5"
                value={color}
                onChange={(e) => setColor(e.target.value)}
              />
            </label>
          </>
        ) : (
          <label className="text-sm space-y-1 block">
            <span className="text-slate-400">Loại danh sách</span>
            <select
              className="w-full bg-ink border border-line rounded-lg px-3 py-2.5"
              value={listType}
              onChange={(e) => setListType(e.target.value as ListType)}
            >
              <option value="allow">Danh sách trắng (cho phép)</option>
              <option value="block">Danh sách đen (chặn)</option>
            </select>
          </label>
        )}

        <label className="sm:col-span-2 lg:col-span-3 flex items-start gap-2 text-sm cursor-pointer select-none">
          <input
            type="checkbox"
            className="mt-1"
            checked={enableWatch}
            onChange={(e) => setEnableWatch(e.target.checked)}
          />
          <span>
            <span className="text-slate-200">Bật truy vết khi đăng ký / thêm</span>
            <span className="block text-xs text-slate-500 mt-0.5">
              Khi camera nhận diện biển này, hệ thống tạo cảnh báo trên dashboard (Truy vết).
            </span>
          </span>
        </label>

        <div className="sm:col-span-2 lg:col-span-3 flex items-end">
          <button
            type="submit"
            className="bg-accent/20 text-accent border border-accent/30 rounded-lg px-4 py-2.5 text-sm"
          >
            {tab === "registry" ? "Đăng ký xe" : "Thêm vào danh sách"}
          </button>
        </div>
      </form>

      {cameras.length > 0 && (
        <div className="flex flex-wrap gap-2 items-center">
          <span className="text-sm text-slate-400">
            {tab === "registry" ? "Đồng bộ quản lý xe lên camera:" : "Đồng bộ danh sách lên camera:"}
          </span>
          {cameras.map((c) => (
            <button
              key={c.id}
              type="button"
              className="text-xs border border-line rounded-lg px-2.5 py-1.5 hover:bg-white/5"
              onClick={async () => {
                try {
                  const res =
                    tab === "registry" ? await api.syncRegistry(c.id) : await api.syncPlates(c.id);
                  setMsg(
                    `Đã đồng bộ ${res.synced} lên «${c.name}»` +
                      (res.errors?.length ? ` · ${res.errors.join("; ")}` : ""),
                  );
                  await refresh();
                } catch (err) {
                  setError(String(err));
                }
              }}
            >
              {c.name}
            </button>
          ))}
        </div>
      )}

      {tab === "registry" ? (
        <RegistryList
          rows={registry}
          watchByPlate={watchByPlate}
          onDelete={async (id) => {
            await api.deleteRegistry(id);
            await refresh();
          }}
          onEnableWatch={async (r) => {
            await api.createWatch({
              plate_number: r.plate_number,
              site_id: r.site_id,
              label: r.brand ? `Đăng ký · ${r.brand}` : `Đăng ký · ${r.group_name}`,
              active: true,
              notify_dashboard: true,
            });
            setMsg(`Đã bật truy vết ${r.plate_number}`);
            await refresh();
          }}
        />
      ) : (
        <ListsTable
          rows={lists}
          watchByPlate={watchByPlate}
          onDelete={async (id) => {
            await api.deletePlate(id);
            await refresh();
          }}
          onEnableWatch={async (r) => {
            await api.createWatch({
              plate_number: r.plate_number,
              site_id: r.site_id,
              label: r.list_type === "allow" ? "Danh sách trắng" : "Danh sách đen",
              active: true,
              notify_dashboard: true,
            });
            setMsg(`Đã bật truy vết ${r.plate_number}`);
            await refresh();
          }}
        />
      )}
    </div>
  );
}

function TabBtn({
  active,
  onClick,
  children,
}: {
  active: boolean;
  onClick: () => void;
  children: ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`text-sm rounded-lg px-3 py-2 border ${
        active
          ? "border-accent/40 bg-accent/15 text-accent"
          : "border-line hover:bg-white/5 text-slate-300"
      }`}
    >
      {children}
    </button>
  );
}

function WatchBadge({ on }: { on: boolean }) {
  if (!on) return <span className="text-slate-600 text-xs">Chưa truy vết</span>;
  return (
    <span className="text-[10px] uppercase tracking-wide px-2 py-0.5 rounded border border-danger/40 text-danger bg-danger/10">
      Đang truy vết
    </span>
  );
}

function RegistryList({
  rows,
  watchByPlate,
  onDelete,
  onEnableWatch,
}: {
  rows: RegistryEntry[];
  watchByPlate: Map<string, PlateWatch>;
  onDelete: (id: string) => Promise<void>;
  onEnableWatch: (r: RegistryEntry) => Promise<void>;
}) {
  return (
    <>
      <div className="md:hidden space-y-2">
        {rows.map((r) => {
          const watched = watchByPlate.has(r.plate_number.toUpperCase());
          return (
            <div key={r.id} className="rounded-xl border border-line bg-panel/70 p-3 text-sm space-y-2">
              <div className="flex items-start justify-between gap-2">
                <div className="font-mono text-lg">{r.plate_number}</div>
                <WatchBadge on={watched} />
              </div>
              <div className="text-slate-400">
                Nhóm {r.group_name} · {r.brand || "—"} · {r.color || "—"} ·{" "}
                {r.synced_to_camera ? "Đã đồng bộ camera" : "Chưa đồng bộ camera"}
              </div>
              <div className="flex gap-3">
                {!watched && (
                  <button type="button" className="text-accent text-xs" onClick={() => onEnableWatch(r)}>
                    Bật truy vết
                  </button>
                )}
                <button type="button" className="text-danger text-xs" onClick={() => onDelete(r.id)}>
                  Xoá
                </button>
              </div>
            </div>
          );
        })}
        {!rows.length && <Empty text="Chưa có xe đăng ký" />}
      </div>

      <div className="hidden md:block overflow-auto rounded-xl border border-line">
        <table className="w-full text-sm">
          <thead className="bg-panel text-slate-400 text-left">
            <tr>
              <th className="px-3 py-2">Biển số</th>
              <th className="px-3 py-2">Nhóm</th>
              <th className="px-3 py-2">Hãng / màu</th>
              <th className="px-3 py-2">Camera</th>
              <th className="px-3 py-2">Truy vết</th>
              <th className="px-3 py-2"></th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => {
              const watched = watchByPlate.has(r.plate_number.toUpperCase());
              return (
                <tr key={r.id} className="border-t border-line/80">
                  <td className="px-3 py-2 font-mono">{r.plate_number}</td>
                  <td className="px-3 py-2">{r.group_name}</td>
                  <td className="px-3 py-2 text-slate-300">
                    {[r.brand, r.color].filter(Boolean).join(" · ") || "—"}
                  </td>
                  <td className="px-3 py-2">{r.synced_to_camera ? "Đã đồng bộ" : "Chưa"}</td>
                  <td className="px-3 py-2">
                    <WatchBadge on={watched} />
                  </td>
                  <td className="px-3 py-2 text-right space-x-3">
                    {!watched && (
                      <button type="button" className="text-accent text-xs" onClick={() => onEnableWatch(r)}>
                        Bật truy vết
                      </button>
                    )}
                    <button type="button" className="text-danger text-xs" onClick={() => onDelete(r.id)}>
                      Xoá
                    </button>
                  </td>
                </tr>
              );
            })}
            {!rows.length && (
              <tr>
                <td colSpan={6} className="px-3 py-8 text-center text-slate-500">
                  Chưa có xe đăng ký
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </>
  );
}

function ListsTable({
  rows,
  watchByPlate,
  onDelete,
  onEnableWatch,
}: {
  rows: PlateList[];
  watchByPlate: Map<string, PlateWatch>;
  onDelete: (id: string) => Promise<void>;
  onEnableWatch: (r: PlateList) => Promise<void>;
}) {
  return (
    <>
      <div className="md:hidden space-y-2">
        {rows.map((r) => {
          const watched = watchByPlate.has(r.plate_number.toUpperCase());
          return (
            <div key={r.id} className="rounded-xl border border-line bg-panel/70 p-3 text-sm space-y-2">
              <div className="flex items-start justify-between gap-2">
                <div className="font-mono text-lg">{r.plate_number}</div>
                <WatchBadge on={watched} />
              </div>
              <div className="text-slate-400">
                {r.list_type === "allow" ? "Danh sách trắng" : "Danh sách đen"} ·{" "}
                {r.synced_to_camera ? "Đã đồng bộ" : "Chưa đồng bộ"}
              </div>
              <div className="flex gap-3">
                {!watched && (
                  <button type="button" className="text-accent text-xs" onClick={() => onEnableWatch(r)}>
                    Bật truy vết
                  </button>
                )}
                <button type="button" className="text-danger text-xs" onClick={() => onDelete(r.id)}>
                  Xoá
                </button>
              </div>
            </div>
          );
        })}
        {!rows.length && <Empty text="Chưa có biển trong danh sách" />}
      </div>

      <div className="hidden md:block overflow-auto rounded-xl border border-line">
        <table className="w-full text-sm">
          <thead className="bg-panel text-slate-400 text-left">
            <tr>
              <th className="px-3 py-2">Biển số</th>
              <th className="px-3 py-2">Loại</th>
              <th className="px-3 py-2">Camera</th>
              <th className="px-3 py-2">Truy vết</th>
              <th className="px-3 py-2"></th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => {
              const watched = watchByPlate.has(r.plate_number.toUpperCase());
              return (
                <tr key={r.id} className="border-t border-line/80">
                  <td className="px-3 py-2 font-mono">{r.plate_number}</td>
                  <td className="px-3 py-2">
                    {r.list_type === "allow" ? "Danh sách trắng" : "Danh sách đen"}
                  </td>
                  <td className="px-3 py-2">{r.synced_to_camera ? "Đã đồng bộ" : "Chưa"}</td>
                  <td className="px-3 py-2">
                    <WatchBadge on={watched} />
                  </td>
                  <td className="px-3 py-2 text-right space-x-3">
                    {!watched && (
                      <button type="button" className="text-accent text-xs" onClick={() => onEnableWatch(r)}>
                        Bật truy vết
                      </button>
                    )}
                    <button type="button" className="text-danger text-xs" onClick={() => onDelete(r.id)}>
                      Xoá
                    </button>
                  </td>
                </tr>
              );
            })}
            {!rows.length && (
              <tr>
                <td colSpan={5} className="px-3 py-8 text-center text-slate-500">
                  Chưa có biển trong danh sách
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </>
  );
}

function Empty({ text }: { text: string }) {
  return (
    <div className="text-slate-500 text-sm border border-dashed border-line rounded-xl p-6 text-center">
      {text}
    </div>
  );
}
