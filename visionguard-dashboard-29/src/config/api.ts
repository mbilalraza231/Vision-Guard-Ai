// API Configuration
// Backend URL: FastAPI at localhost:8000

export const API_CONFIG = {
  // Base URL for the REST API — direct to FastAPI backend
  baseUrl: 'http://localhost:8000',

  // WebSocket URL derived from the same backend origin
  wsUrl: 'ws://localhost:8000',

  // Request timeout in milliseconds
  timeout: 30000,

  // Retry configuration
  retry: {
    maxAttempts: 3,
    baseDelay: 1000,
  },
};

// API Endpoints — mapped to real FastAPI backend
export const API_ENDPOINTS = {
  // Health
  health: '/health',

  // Dashboard endpoints (mapped to real backend)
  dashboard: {
    stats: '/events/stats',
    systemMetrics: '/status',
    recentEvents: '/events',
  },

  // Events / Incidents endpoints
  incidents: {
    list: '/events',
    byId: (id: string) => `/events/${id}`,
    stats: '/events/stats',
    evidence: (id: string) => `/events/${id}/evidence`,
  },

  // Cameras endpoints
  cameras: {
    list: '/cameras',
    start: (id: string) => `/cameras/${id}/start`,
    stop: (id: string) => `/cameras/${id}/stop`,
    register: '/cameras/register',
  },

  // ECS endpoints
  ecs: {
    start: '/ecs/start',
    stop: '/ecs/stop',
    status: '/ecs/status',
  },

  // Alerts endpoints
  alerts: {
    list: '/alerts',
  },

  // Detection images endpoints
  detections: {
    latest: '/detections/latest',
    image: (filename: string) => `/detections/images/${filename}`,
    boxes: '/detections/boxes',
  },
};

// Build full API URL — no version prefix
export function buildApiUrl(endpoint: string): string {
  return `${API_CONFIG.baseUrl}${endpoint}`;
}

export function buildWsUrl(endpoint = ''): string {
  const base = API_CONFIG.wsUrl.replace(/\/$/, '');
  const path = endpoint.startsWith('/') ? endpoint : `/${endpoint}`;
  return `${base}${path}`;
}
