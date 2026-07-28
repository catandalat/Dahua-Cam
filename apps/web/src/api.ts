const API_URL = import.meta.env.VITE_API_URL || "http://localhost:8000";
export const WS_URL = import.meta.env.VITE_WS_URL || "ws://localhost:8000/ws/live";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, {
    headers: { "Content-Type": "application/json", ...(init?.headers || {}) },
    ...init,
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || res.statusText);
  }
  if (res.status === 204) return undefined as T;
  return res.json();
}

export const api = {
  health: () => request<{ status: string }>("/health"),
  overview: () => request<Overview>("/stats/overview"),
  detections: (q = "") => request<Detection[]>(`/detections${q}`),
  sessions: (q = "") => request<Session[]>(`/sessions${q}`),
  sessionStats: (q = "") => request<SessionStats>(`/sessions/stats${q}`),
  vehicleStats: (q = "") => request<VehicleStats>(`/stats/vehicles${q}`),
  violations: (q = "") => request<Violation[]>(`/violations${q}`),
  cameras: () => request<Camera[]>("/cameras"),
  sites: () => request<Site[]>("/sites"),
  gates: (siteId?: string) =>
    request<Gate[]>(siteId ? `/gates?site_id=${siteId}` : "/gates"),
  lanes: (gateId?: string) =>
    request<Lane[]>(gateId ? `/lanes?gate_id=${gateId}` : "/lanes"),
  createSite: (body: { name: string }) =>
    request<Site>("/sites", { method: "POST", body: JSON.stringify(body) }),
  createGate: (body: { site_id: string; name: string }) =>
    request<Gate>("/gates", { method: "POST", body: JSON.stringify(body) }),
  createLane: (body: { gate_id: string; name: string; lane_number?: number }) =>
    request<Lane>("/lanes", { method: "POST", body: JSON.stringify(body) }),
  createCamera: (body: Record<string, unknown>) =>
    request<Camera>("/cameras", { method: "POST", body: JSON.stringify(body) }),
  updateCamera: (id: string, body: Record<string, unknown>) =>
    request<Camera>(`/cameras/${id}`, { method: "PATCH", body: JSON.stringify(body) }),
  deleteCamera: (id: string) =>
    request<{ status: string }>(`/cameras/${id}`, { method: "DELETE" }),
  ingestDetection: (body: Record<string, unknown>) =>
    request<Record<string, unknown>>("/ingest/detection", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  probeCaps: (id: string) =>
    request<{ supported_codes: string[]; suggested_subscribe: string[] }>(
      `/cameras/${id}/probe-caps`,
      { method: "POST" },
    ),
  plateLists: (q = "") => request<PlateList[]>(`/plate-lists${q}`),
  createPlate: (body: { site_id: string; list_type: string; plate_number: string; note?: string }) =>
    request<PlateList>("/plate-lists", { method: "POST", body: JSON.stringify(body) }),
  deletePlate: (id: string) => request<{ status: string }>(`/plate-lists/${id}`, { method: "DELETE" }),
  syncPlates: (cameraId: string) =>
    request<{ synced: number; errors: string[] }>(`/plate-lists/sync/${cameraId}`, {
      method: "POST",
    }),
  exportDetectionsUrl: (days = 1) => `${API_URL}/export/detections.csv?days=${days}`,
  exportSessionsUrl: (days = 7) => `${API_URL}/export/sessions.csv?days=${days}`,
  mediaUrl: (detectionId: string, kind = "plate") =>
    `${API_URL}/media/${detectionId}/${kind}`,
  flow: (q = "") => request<FlowSample[]>(`/flow${q}`),
  flowByLane: (q = "") => request<FlowByLane[]>(`/flow/by-lane${q}`),
  jams: (q = "") => request<JamEvent[]>(`/jams${q}`),
  registry: (q = "") => request<RegistryEntry[]>(`/vehicle-registry${q}`),
  createRegistry: (body: Record<string, unknown>) =>
    request<RegistryEntry>("/vehicle-registry", { method: "POST", body: JSON.stringify(body) }),
  deleteRegistry: (id: string) =>
    request<{ status: string }>(`/vehicle-registry/${id}`, { method: "DELETE" }),
  syncRegistry: (cameraId: string) =>
    request<{ synced: number; errors: string[] }>(`/vehicle-registry/sync/${cameraId}`, {
      method: "POST",
    }),
  cameraRtsp: (id: string) => request<{ rtsp_url: string; rtsp_url_sub: string; note: string }>(`/cameras/${id}/rtsp`),
  cameraDeviceInfo: (id: string) => request<{ info: Record<string, unknown> }>(`/cameras/${id}/device-info`),
  snapshotUrl: (id: string) => `${API_URL}/cameras/${id}/snapshot`,
  manualSnapUrl: (id: string) => `${API_URL}/cameras/${id}/manual-snap`,
  strobe: (id: string, action: "open" | "close") =>
    request(`/cameras/${id}/strobe/${action}`, { method: "POST" }),
  setSpeedLimit: (id: string, body: {
    min_speed: number;
    max_speed: number;
    alert_overspeed?: boolean;
    alert_underspeed?: boolean;
    push_to_camera?: boolean;
  }) =>
    request<SpeedPolicy>(`/cameras/${id}/speed-limit`, { method: "POST", body: JSON.stringify(body) }),
  getSpeedPolicy: (id: string) => request<SpeedPolicy>(`/cameras/${id}/speed-policy`),
  saveSpeedPolicy: (id: string, body: Record<string, unknown>) =>
    request<SpeedPolicy & { warning?: string; status?: string }>(`/cameras/${id}/speed-policy`, {
      method: "PUT",
      body: JSON.stringify(body),
    }),
  speedPolicies: () => request<SpeedPolicy[]>("/speed/policies"),
  speedStats: (q = "?hours=24") => request<SpeedStats>(`/speed/stats${q}`),
  speedMeasurements: (q = "") => request<SpeedMeasurement[]>(`/speed/measurements${q}`),
  getSpeedLimit: (id: string) => request<SpeedPolicy>(`/cameras/${id}/speed-limit`),
  setUnlicensed: (id: string, enable: boolean) =>
    request(`/cameras/${id}/unlicensed-detection`, {
      method: "POST",
      body: JSON.stringify({ enable }),
    }),
  pullFlowHistory: (id: string, hours = 2) =>
    request(`/cameras/${id}/flow/pull-history?hours=${hours}`, { method: "POST" }),
  parking: (id: string) => request<{ status: Record<string, unknown> }>(`/cameras/${id}/parking`),
  watches: (q = "") => request<PlateWatch[]>(`/watches${q}`),
  createWatch: (body: Record<string, unknown>) =>
    request<PlateWatch>("/watches", { method: "POST", body: JSON.stringify(body) }),
  updateWatch: (id: string, body: Record<string, unknown>) =>
    request<PlateWatch>(`/watches/${id}`, { method: "PATCH", body: JSON.stringify(body) }),
  deleteWatch: (id: string) => request<{ status: string }>(`/watches/${id}`, { method: "DELETE" }),
  watchAlerts: (q = "") => request<WatchAlert[]>(`/watch-alerts${q}`),
  watchUnreadCount: () => request<{ count: number }>("/watch-alerts/unread-count"),
  markAlertRead: (id: string) =>
    request<WatchAlert>(`/watch-alerts/${id}/read`, { method: "POST" }),
  markAllAlertsRead: () =>
    request<{ marked: number }>("/watch-alerts/read-all", { method: "POST" }),
  mapCameras: () => request<MapCamerasResponse>("/map/cameras"),
  setCameraLocation: (
    id: string,
    body: { latitude: number; longitude: number; map_icon?: string; map_note?: string },
  ) =>
    request<Camera>(`/cameras/${id}/location`, { method: "PUT", body: JSON.stringify(body) }),
  clearCameraLocation: (id: string) =>
    request<Camera>(`/cameras/${id}/location`, { method: "DELETE" }),
  getOverlay: (cameraId: string) =>
    request<{ camera_id: string; shapes: OverlayShape[]; enabled: boolean }>(
      `/cameras/${cameraId}/overlay`,
    ),
  saveOverlay: (cameraId: string, body: { shapes: OverlayShape[]; enabled?: boolean }) =>
    request<{ camera_id: string; shapes: OverlayShape[]; enabled: boolean }>(
      `/cameras/${cameraId}/overlay`,
      { method: "PUT", body: JSON.stringify(body) },
    ),
  liveDetections: (cameraId: string, limit = 3) =>
    request<LiveDetection[]>(`/cameras/${cameraId}/live-detections?limit=${limit}&max_age_sec=12`),
};

export type OverlayShape = {
  id: string;
  type: "lane_line" | "stop_line" | "region";
  label?: string;
  color?: string;
  points: number[][];
};

export type LiveDetection = {
  id: string;
  plate_number?: string;
  event_utc?: string;
  vehicle_class?: string;
  vehicle_brand?: string;
  vehicle_color?: string;
  passage_direction?: string;
  plate_bbox?: number[];
  vehicle_bbox?: number[];
  image_paths?: Record<string, string>;
};

export type SpeedPolicy = {
  camera_id: string;
  camera_name: string;
  min_speed: number;
  max_speed: number;
  alert_overspeed: boolean;
  alert_underspeed: boolean;
  push_to_camera: boolean;
  last_synced_at?: string | null;
  updated_at?: string | null;
  device?: Record<string, unknown>;
  device_norm?: { min?: number | null; max?: number | null };
  device_error?: string;
  warning?: string;
};

export type SpeedStats = {
  hours: number;
  samples: number;
  avg_speed?: number | null;
  max_speed?: number | null;
  min_speed?: number | null;
  overspeed_count: number;
  underspeed_count: number;
};

export type SpeedMeasurement = {
  id: string;
  camera_id: string;
  camera_name?: string;
  plate_number?: string;
  speed: number;
  limit_min?: number | null;
  limit_max?: number | null;
  status: string;
  over_pct?: number | null;
  event_utc?: string;
  vehicle_class?: string;
  image_paths?: Record<string, string>;
};

export type SpeedAlert = {
  id: string;
  kind: string;
  plate_number?: string;
  speed?: number;
  peak_speed?: number | null;
  limit_max?: number | null;
  limit_min?: number | null;
  over_pct?: number | null;
  camera_id: string;
  camera_name?: string;
  detection_id?: string;
  image_kind?: string | null;
  message: string;
  event_utc?: string;
  updated_peak?: boolean;
};

export type PlateWatch = {
  id: string;
  site_id?: string | null;
  plate_number: string;
  label?: string;
  note?: string;
  priority: string;
  active: boolean;
  notify_dashboard: boolean;
  created_at?: string;
};

export type WatchAlert = {
  id: string;
  watch_id: string;
  detection_id?: string;
  camera_id: string;
  camera_name?: string;
  site_id: string;
  plate_number: string;
  priority: string;
  label?: string;
  message: string;
  event_utc?: string;
  image_paths?: Record<string, string>;
  read: boolean;
  created_at?: string;
};

export type FlowSample = {
  id: string;
  camera_id: string;
  lane_number?: number;
  vehicles_num?: number;
  queue_len?: number;
  direction?: string;
  event_utc?: string;
  event_code?: string;
};

export type FlowByLane = {
  lane_number?: number;
  direction?: string;
  vehicles_sum: number;
  samples: number;
};

export type JamEvent = {
  id: string;
  camera_id: string;
  jam_length_pct?: number;
  jam_real_length_m?: number;
  lane_number?: number;
  event_utc?: string;
};

export type RegistryEntry = {
  id: string;
  site_id: string;
  group_name: string;
  plate_number: string;
  brand?: string;
  color?: string;
  note?: string;
  synced_to_camera?: boolean;
};

export type Overview = {
  detections_24h: number;
  violations_24h: number;
  vehicles_inside: number;
  cameras_enabled: number;
  cameras_connected: number;
};

export type Detection = {
  id: string;
  camera_id: string;
  site_id: string;
  event_code?: string;
  event_utc?: string;
  plate_number?: string;
  plate_color?: string;
  vehicle_brand?: string;
  vehicle_model?: string;
  vehicle_category?: string;
  vehicle_class?: string;
  vehicle_color?: string;
  speed?: number;
  speed_status?: string;
  limit_max?: number | null;
  limit_min?: number | null;
  passage_direction?: string;
  seatbelt_main?: string;
  calling?: boolean;
  smoking?: boolean;
  image_paths?: Record<string, string>;
  unlicensed?: boolean;
  watched?: boolean;
  meta?: Record<string, unknown>;
};

export type Session = {
  id: string;
  plate_number: string;
  status: string;
  entered_at?: string;
  exited_at?: string;
  vehicle_brand?: string;
  vehicle_color?: string;
  entry_speed?: number | null;
  exit_speed?: number | null;
  overstay?: boolean;
  duration_sec?: number;
};

export type SessionStats = {
  entries: number;
  exits: number;
  inside: number;
  hourly: { hour?: string; direction?: string; count: number }[];
};

export type VehicleStats = {
  days: number;
  by_class: { key: string; count: number }[];
  by_color: { key: string; count: number }[];
  by_brand: { key: string; count: number }[];
  by_category: { key: string; count: number }[];
};

export type Violation = {
  id: string;
  violation_type: string;
  plate_number?: string;
  event_utc?: string;
  camera_id: string;
  detail?: Record<string, unknown>;
  image_paths?: Record<string, string>;
  detection_id?: string;
};

export type Camera = {
  id: string;
  site_id: string;
  lane_id?: string;
  name: string;
  host: string;
  port: number;
  direction_role: string;
  enabled: boolean;
  subscribe_codes?: string[];
  listener_status: string;
  listener_error?: string;
  last_event_at?: string;
  latitude?: number | null;
  longitude?: number | null;
  map_icon?: string;
  map_note?: string | null;
  caps?: { supported_codes?: string[]; probed_at?: string };
};

export type MapCamerasResponse = {
  center: { lat: number; lng: number };
  style_url: string;
  placed: Camera[];
  unplaced: Camera[];
};

export type Site = { id: string; name: string; timezone: string };
export type Gate = { id: string; site_id: string; name: string };
export type Lane = { id: string; gate_id: string; name: string; lane_number?: number };
export type PlateList = {
  id: string;
  site_id: string;
  list_type: string;
  plate_number: string;
  note?: string;
  synced_to_camera?: boolean;
};
