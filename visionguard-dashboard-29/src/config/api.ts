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
    notes: (id: string) => `/events/${id}/notes`,
    acknowledge: (id: string) => `/events/${id}/acknowledge`,
    resolve: (id: string) => `/events/${id}/resolve`,
  },

  // Cameras endpoints
  cameras: {
    list: '/cameras',
    start: (id: string) => `/cameras/${id}/start`,
    stop: (id: string) => `/cameras/${id}/stop`,
    register: '/cameras/register',
    delete: (id: string) => `/cameras/${id}`,
  },

  // ECS endpoints
  ecs: {
    start: '/ecs/start',
    stop: '/ecs/stop',
    status: '/ecs/status',
  },


  alerts: {
    list: '/alerts',
    contacts: {
      list: '/api/v1/alert-recipients',
      create: '/api/v1/alert-recipients',
      update: (id: string) => `/api/v1/alert-recipients/${id}`,
      delete: (id: string) => `/api/v1/alert-recipients/${id}`,
    },
  },

  // Zones endpoints
  zones: {
    list: '/api/v1/zones',
    create: '/api/v1/zones',
    update: (id: string) => `/api/v1/zones/${id}`,
    delete: (id: string) => `/api/v1/zones/${id}`,
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
