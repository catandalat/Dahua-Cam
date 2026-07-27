import { useCallback, useEffect, useMemo, useState, type ReactNode } from "react";
import { Link } from "react-router-dom";
import Map, { Marker, NavigationControl, Popup } from "react-map-gl/maplibre";
import maplibregl from "maplibre-gl";
import maplibreWorkerUrl from "maplibre-gl/dist/maplibre-gl-csp-worker.js?url";
import "maplibre-gl/dist/maplibre-gl.css";
import { api, Camera, MapCamerasResponse } from "../api";
import { CameraMapIcon, ICON_OPTIONS, statusColor } from "../components/CameraMapIcon";

const STYLE_URL = "https://tiles.openfreemap.org/styles/liberty";

maplibregl.setWorkerUrl(maplibreWorkerUrl);

const ROLE_LABEL: Record<string, string> = {
  entry: "Vào",
  exit: "Ra",
  bidirectional: "Hai chiều",
};

type UserPos = { latitude: number; longitude: number; accuracy?: number };

export default function MapPage() {
  const [data, setData] = useState<MapCamerasResponse | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const [placingId, setPlacingId] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [iconDraft, setIconDraft] = useState("camera");
  const [userPos, setUserPos] = useState<UserPos | null>(null);
  const [locating, setLocating] = useState(false);
  const [viewState, setViewState] = useState({
    longitude: 106.7009,
    latitude: 10.7769,
    zoom: 13,
  });

  const load = useCallback(async () => {
    const res = await api.mapCameras();
    setData(res);
    if (res.placed.length) {
      setViewState((v) => ({
        ...v,
        longitude: res.center.lng,
        latitude: res.center.lat,
        zoom: res.placed.length === 1 ? 15 : Math.max(12, v.zoom),
      }));
    }
  }, []);

  useEffect(() => {
    load().catch((e) => setMsg(String(e)));
    const t = setInterval(() => load().catch(() => null), 12000);
    return () => clearInterval(t);
  }, [load]);

  const selected = useMemo(() => {
    if (!data || !selectedId) return null;
    return [...data.placed, ...data.unplaced].find((c) => c.id === selectedId) || null;
  }, [data, selectedId]);

  const goToUserLocation = useCallback(() => {
    if (!navigator.geolocation) {
      setMsg("Trình duyệt không hỗ trợ định vị GPS");
      return;
    }
    setLocating(true);
    setMsg("Đang lấy vị trí hiện tại…");
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        const next: UserPos = {
          latitude: pos.coords.latitude,
          longitude: pos.coords.longitude,
          accuracy: pos.coords.accuracy,
        };
        setUserPos(next);
        setViewState((v) => ({
          ...v,
          latitude: next.latitude,
          longitude: next.longitude,
          zoom: Math.max(v.zoom, 16),
        }));
        const acc =
          typeof next.accuracy === "number" ? ` (±${Math.round(next.accuracy)} m)` : "";
        setMsg(`Đã định vị vị trí của bạn${acc}`);
        setLocating(false);
      },
      (err) => {
        const hint =
          err.code === err.PERMISSION_DENIED
            ? "Hãy cho phép truy cập vị trí trong trình duyệt"
            : err.code === err.TIMEOUT
              ? "Hết thời gian chờ GPS — thử lại"
              : "Không lấy được vị trí";
        setMsg(hint);
        setLocating(false);
      },
      { enableHighAccuracy: true, timeout: 15000, maximumAge: 10000 },
    );
  }, []);

  const placeAt = async (lat: number, lng: number, cameraId: string) => {
    try {
      await api.setCameraLocation(cameraId, {
        latitude: lat,
        longitude: lng,
        map_icon: iconDraft,
      });
      setMsg(`Đã gắn ${cameraId.slice(0, 8)}… lên bản đồ`);
      setPlacingId(null);
      setSelectedId(cameraId);
      await load();
    } catch (e) {
      setMsg(String(e));
    }
  };

  const placeAtUserLocation = async () => {
    if (!placingId) return;

    const place = (lat: number, lng: number) => placeAt(lat, lng, placingId);

    if (userPos) {
      await place(userPos.latitude, userPos.longitude);
      return;
    }

    if (!navigator.geolocation) {
      setMsg("Trình duyệt không hỗ trợ định vị GPS");
      return;
    }

    setLocating(true);
    setMsg("Đang lấy vị trí để gắn camera…");
    navigator.geolocation.getCurrentPosition(
      async (pos) => {
        const next: UserPos = {
          latitude: pos.coords.latitude,
          longitude: pos.coords.longitude,
          accuracy: pos.coords.accuracy,
        };
        setUserPos(next);
        setViewState((v) => ({
          ...v,
          latitude: next.latitude,
          longitude: next.longitude,
          zoom: Math.max(v.zoom, 16),
        }));
        setLocating(false);
        await place(next.latitude, next.longitude);
      },
      (err) => {
        const hint =
          err.code === err.PERMISSION_DENIED
            ? "Hãy cho phép truy cập vị trí trong trình duyệt"
            : "Không lấy được vị trí để gắn camera";
        setMsg(hint);
        setLocating(false);
      },
      { enableHighAccuracy: true, timeout: 15000, maximumAge: 10000 },
    );
  };

  const onMapClick = async (e: { lngLat: { lat: number; lng: number } }) => {
    if (!placingId) return;
    await placeAt(e.lngLat.lat, e.lngLat.lng, placingId);
  };

  const onMarkerDragEnd = async (camera: Camera, lat: number, lng: number) => {
    try {
      await api.setCameraLocation(camera.id, {
        latitude: lat,
        longitude: lng,
        map_icon: camera.map_icon || "camera",
      });
      await load();
    } catch (e) {
      setMsg(String(e));
    }
  };

  const clearLocation = async (id: string) => {
    if (!confirm("Gỡ camera khỏi bản đồ?")) return;
    await api.clearCameraLocation(id);
    setSelectedId(null);
    await load();
  };

  const updateIcon = async (id: string, map_icon: string) => {
    const cam = data?.placed.find((c) => c.id === id);
    if (!cam || cam.latitude == null || cam.longitude == null) {
      setIconDraft(map_icon);
      return;
    }
    await api.setCameraLocation(id, {
      latitude: cam.latitude,
      longitude: cam.longitude,
      map_icon,
    });
    await load();
  };

  return (
    <div className="space-y-3 md:space-y-4 h-[calc(100vh-5.5rem)] md:h-[calc(100vh-3rem)] flex flex-col min-h-[28rem]">
      <header className="flex flex-col sm:flex-row sm:items-end justify-between gap-2 shrink-0">
        <div>
          <h2 className="text-xl md:text-2xl font-semibold">Bản đồ camera</h2>
          <p className="text-slate-400 text-sm mt-1">
            OpenFreeMap Liberty · chọn camera rồi bấm lên bản đồ để gắn vị trí
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <button
            type="button"
            onClick={goToUserLocation}
            disabled={locating}
            className="text-sm rounded-lg border border-line bg-panel px-3 py-2 hover:bg-white/5 disabled:opacity-50 inline-flex items-center gap-2"
            title="Bay tới vị trí GPS của bạn"
          >
            <LocateIcon spinning={locating} />
            {locating ? "Đang định vị…" : "Vị trí của tôi"}
          </button>
          {placingId && (
            <div className="text-sm text-accent border border-accent/40 bg-accent/10 rounded-lg px-3 py-2 flex flex-wrap items-center gap-2">
              <span>Đang gắn vị trí — bấm vào bản đồ</span>
              <button
                type="button"
                className="underline font-medium"
                onClick={() => placeAtUserLocation()}
              >
                Gắn tại vị trí của tôi
              </button>
              <button type="button" className="underline opacity-80" onClick={() => setPlacingId(null)}>
                Huỷ
              </button>
            </div>
          )}
        </div>
      </header>

      {msg && (
        <div className="text-sm border border-line rounded-lg px-3 py-2 break-words shrink-0">{msg}</div>
      )}

      <div className="flex-1 min-h-0 grid grid-cols-1 lg:grid-cols-[280px_1fr] gap-3">
        <aside className="rounded-xl border border-line bg-panel/80 overflow-auto order-2 lg:order-1 max-h-56 lg:max-h-none">
          <div className="p-3 border-b border-line sticky top-0 bg-panel/95 backdrop-blur z-10">
            <div className="text-xs uppercase tracking-wide text-slate-500 mb-2">Icon khi gắn</div>
            <div className="flex flex-wrap gap-1.5">
              {ICON_OPTIONS.map((opt) => (
                <button
                  key={opt.id}
                  type="button"
                  title={opt.label}
                  onClick={() => {
                    setIconDraft(opt.id);
                    if (selectedId) updateIcon(selectedId, opt.id).catch((e) => setMsg(String(e)));
                  }}
                  className={`rounded-lg border p-1.5 ${
                    iconDraft === opt.id ? "border-accent bg-accent/15" : "border-line hover:bg-white/5"
                  }`}
                >
                  <CameraMapIcon icon={opt.id} status="connected" size={28} />
                </button>
              ))}
            </div>
          </div>

          <div className="p-3 space-y-3">
            <Section title={`Trên bản đồ (${data?.placed.length ?? 0})`}>
              {(data?.placed || []).map((c) => (
                <CamRow
                  key={c.id}
                  camera={c}
                  active={selectedId === c.id}
                  onSelect={() => {
                    setSelectedId(c.id);
                    setIconDraft(c.map_icon || "camera");
                    if (c.longitude != null && c.latitude != null) {
                      setViewState((v) => ({
                        ...v,
                        longitude: c.longitude!,
                        latitude: c.latitude!,
                        zoom: Math.max(v.zoom, 15),
                      }));
                    }
                  }}
                  actionLabel="Định vị lại"
                  onAction={() => {
                    setPlacingId(c.id);
                    setSelectedId(c.id);
                    setIconDraft(c.map_icon || "camera");
                  }}
                />
              ))}
              {!data?.placed.length && (
                <p className="text-xs text-slate-500">Chưa có camera trên bản đồ</p>
              )}
            </Section>

            <Section title={`Chưa gắn (${data?.unplaced.length ?? 0})`}>
              {(data?.unplaced || []).map((c) => (
                <CamRow
                  key={c.id}
                  camera={c}
                  active={placingId === c.id}
                  onSelect={() => setSelectedId(c.id)}
                  actionLabel="Gắn lên bản đồ"
                  onAction={() => {
                    setPlacingId(c.id);
                    setSelectedId(c.id);
                    setIconDraft(c.map_icon || "camera");
                    setMsg(`Chọn vị trí trên bản đồ cho «${c.name}»`);
                  }}
                />
              ))}
              {!data?.unplaced.length && (
                <p className="text-xs text-slate-500">Tất cả camera đã có vị trí</p>
              )}
            </Section>
          </div>
        </aside>

        <div
          className={`relative rounded-xl border overflow-hidden order-1 lg:order-2 min-h-[22rem] ${
            placingId ? "border-accent ring-2 ring-accent/30" : "border-line"
          }`}
        >
          <Map
            {...viewState}
            mapLib={maplibregl}
            onMove={(evt) => setViewState(evt.viewState)}
            onClick={onMapClick}
            mapStyle={data?.style_url || STYLE_URL}
            style={{ width: "100%", height: "100%" }}
            cursor={placingId ? "crosshair" : "grab"}
          >
            <NavigationControl position="top-right" />

            {userPos && (
              <Marker
                latitude={userPos.latitude}
                longitude={userPos.longitude}
                anchor="center"
                style={{ zIndex: 1 }}
              >
                <div className="relative pointer-events-none" title="Vị trí của bạn">
                  {typeof userPos.accuracy === "number" && userPos.accuracy > 0 && (
                    <div
                      className="absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 rounded-full bg-sky-400/20 border border-sky-400/40"
                      style={{
                        width: Math.min(120, Math.max(28, userPos.accuracy / 2)),
                        height: Math.min(120, Math.max(28, userPos.accuracy / 2)),
                      }}
                    />
                  )}
                  <div className="relative w-4 h-4 rounded-full bg-sky-500 border-2 border-white shadow-lg ring-4 ring-sky-400/35" />
                </div>
              </Marker>
            )}

            {(data?.placed || []).map((c) =>
              c.latitude != null && c.longitude != null ? (
                <Marker
                  key={c.id}
                  latitude={c.latitude}
                  longitude={c.longitude}
                  anchor="bottom"
                  draggable
                  onClick={(e) => {
                    e.originalEvent.stopPropagation();
                    setSelectedId(c.id);
                    setIconDraft(c.map_icon || "camera");
                  }}
                  onDragEnd={(e) => {
                    onMarkerDragEnd(c, e.lngLat.lat, e.lngLat.lng);
                  }}
                >
                  <div className="relative group cursor-pointer drop-shadow-lg">
                    <CameraMapIcon
                      icon={c.map_icon || "camera"}
                      status={c.listener_status}
                      size={selectedId === c.id ? 48 : 42}
                      pulse={c.listener_status === "connected"}
                    />
                    <div className="absolute left-1/2 -translate-x-1/2 -bottom-5 whitespace-nowrap text-[10px] font-medium bg-black/70 text-white px-1.5 py-0.5 rounded opacity-90 group-hover:opacity-100">
                      {c.name}
                    </div>
                  </div>
                </Marker>
              ) : null,
            )}

            {selected && selected.latitude != null && selected.longitude != null && (
              <Popup
                latitude={selected.latitude}
                longitude={selected.longitude}
                anchor="top"
                offset={16}
                onClose={() => setSelectedId(null)}
                closeOnClick={false}
                className="camera-map-popup"
              >
                <div className="text-slate-900 min-w-[11rem] max-w-[16rem]">
                  <div className="font-semibold text-sm">{selected.name}</div>
                  <div className="text-xs text-slate-600 font-mono mt-0.5">
                    {selected.host}:{selected.port}
                  </div>
                  <div className="text-xs mt-1.5 flex flex-wrap gap-1">
                    <span className="rounded bg-slate-100 px-1.5 py-0.5">
                      {ROLE_LABEL[selected.direction_role] || selected.direction_role}
                    </span>
                    <span
                      className="rounded px-1.5 py-0.5 text-white"
                      style={{ background: statusColor(selected.listener_status) }}
                    >
                      {selected.listener_status}
                    </span>
                  </div>
                  {selected.map_note && (
                    <p className="text-xs text-slate-600 mt-1">{selected.map_note}</p>
                  )}
                  <div className="mt-2 flex flex-wrap gap-1.5">
                    <Link
                      to={`/monitor?camera=${selected.id}`}
                      className="text-[11px] rounded bg-sky-600 text-white px-2 py-1"
                    >
                      Quan sát
                    </Link>
                    <Link
                      to="/cameras"
                      className="text-[11px] rounded border border-slate-300 px-2 py-1"
                    >
                      Camera
                    </Link>
                    <button
                      type="button"
                      className="text-[11px] rounded border border-red-200 text-red-600 px-2 py-1"
                      onClick={() => clearLocation(selected.id)}
                    >
                      Gỡ
                    </button>
                  </div>
                </div>
              </Popup>
            )}
          </Map>

          <div className="absolute top-3 left-3 z-10 flex flex-col gap-2">
            <button
              type="button"
              onClick={goToUserLocation}
              disabled={locating}
              className="shadow-md rounded-lg border border-slate-200 bg-white text-slate-800 px-2.5 py-2 text-xs font-medium hover:bg-slate-50 disabled:opacity-60 inline-flex items-center gap-1.5"
              title="Vị trí của tôi"
            >
              <LocateIcon spinning={locating} dark />
              {locating ? "…" : "GPS"}
            </button>
          </div>

          <div className="absolute bottom-2 left-2 text-[10px] text-slate-700 bg-white/80 rounded px-1.5 py-0.5 pointer-events-none">
            © OpenStreetMap · OpenFreeMap
          </div>
        </div>
      </div>
    </div>
  );
}

function LocateIcon({ spinning, dark }: { spinning?: boolean; dark?: boolean }) {
  return (
    <svg
      viewBox="0 0 24 24"
      className={`w-4 h-4 ${spinning ? "animate-pulse" : ""} ${dark ? "text-sky-600" : "text-accent"}`}
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      aria-hidden
    >
      <circle cx="12" cy="12" r="3" />
      <path d="M12 2v3M12 19v3M2 12h3M19 12h3" strokeLinecap="round" />
      <circle cx="12" cy="12" r="8" opacity="0.45" />
    </svg>
  );
}

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div>
      <div className="text-xs uppercase tracking-wide text-slate-500 mb-1.5">{title}</div>
      <div className="space-y-1.5">{children}</div>
    </div>
  );
}

function CamRow({
  camera,
  active,
  onSelect,
  actionLabel,
  onAction,
}: {
  camera: Camera;
  active?: boolean;
  onSelect: () => void;
  actionLabel: string;
  onAction: () => void;
}) {
  return (
    <div
      className={`rounded-lg border px-2.5 py-2 ${
        active ? "border-accent/50 bg-accent/10" : "border-line"
      }`}
    >
      <button type="button" className="w-full text-left" onClick={onSelect}>
        <div className="flex items-center gap-2">
          <CameraMapIcon
            icon={camera.map_icon || "camera"}
            status={camera.listener_status}
            size={26}
          />
          <div className="min-w-0">
            <div className="text-sm font-medium truncate">{camera.name}</div>
            <div className="text-[10px] text-slate-500 font-mono truncate">
              {camera.host} · {ROLE_LABEL[camera.direction_role] || camera.direction_role}
            </div>
          </div>
        </div>
      </button>
      <button
        type="button"
        onClick={onAction}
        className="mt-1.5 w-full text-xs border border-line rounded-md py-1 hover:bg-white/5"
      >
        {actionLabel}
      </button>
    </div>
  );
}
