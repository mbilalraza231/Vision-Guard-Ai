// User and Authentication Types
export interface User {
  id: string;
  email: string;
  name: string;
  role: UserRole;
  status: 'active' | 'inactive';
  avatar?: string;
  createdAt: string;
}

export type UserRole = 'admin' | 'manager' | 'officer' | 'viewer';

export interface AuthState {
  user: User | null;
  isAuthenticated: boolean;
  isLoading: boolean;
}

export interface LoginCredentials {
  email: string;
  password: string;
}

export interface AuthTokens {
  accessToken: string;
  refreshToken?: string;
}

// Incident Types
export interface Incident {
  id: string;
  time: string;
  camera: Camera;
  type: IncidentType;
  severity: Severity;
  status: IncidentStatus;
  description?: string;
  zone?: Zone;
  thumbnailUrl?: string;
  videoUrl?: string;
  createdAt: string;
  updatedAt: string;
}

export type IncidentType = 'fire' | 'weapon' | 'fall' | 'intrusion' | 'vandalism' | 'loitering';
export type Severity = 'critical' | 'high' | 'medium' | 'low';
export type IncidentStatus = 'active' | 'acknowledged' | 'resolved';

// Camera Types
export interface Camera {
  id: string;
  name: string;
  location: string;
  status: CameraStatus;
  aiActive: boolean;
  zone?: Zone;
  streamUrl?: string;
  lastActivity?: string;
}

export type CameraStatus = 'online' | 'offline' | 'maintenance';

// Zone Types
export interface Zone {
  id: string;
  name: string;
  cameras: Camera[];
  activeHours: string;
  alertRecipients: number;
  detectionPriority: DetectionPriority;
  recentActivity: number;
}

export interface DetectionPriority {
  fire: Severity;
  weapon: Severity;
  fall: Severity;
  intrusion: Severity;
}

// Analytics Types
export interface SystemMetrics {
  cpuUsage: number;
  cpuCores: string;
  memoryUsed: number;
  memoryTotal: number;
  storageUsed: number;
  storageTotal: number;
  incidentsStored: number;
  isOperational: boolean;
  lastUpdated: string;
}

export interface DashboardStats {
  activeCameras: {
    online: number;
    total: number;
  };
  todayIncidents: {
    count: number;
    change: number;
  };
  criticalAlerts: {
    count: number;
    requiresAttention: number;
  };
  avgAccuracy: {
    percentage: number;
    period: string;
  };
}

export interface AnalyticsData {
  totalIncidents: number;
  incidentsChange: number;
  avgResponseTime: string;
  responseTimeChange: number;
  falsePositiveRate: number;
  falsePositiveChange: number;
  systemUptime: number;
  uptimeDowntime: string;
  detectionAccuracyTrend: TrendDataPoint[];
  detectionByType: DetectionByTypeData[];
  performanceMetrics: PerformanceMetric[];
}

export interface TrendDataPoint {
  day: string;
  accuracy: number;
}

export interface DetectionByTypeData {
  type: IncidentType;
  count: number;
}

export interface PerformanceMetric {
  metric: string;
  target: string;
  current: string;
  status: 'good' | 'warning' | 'critical';
}

// Settings Types
export interface SystemSettings {
  general: GeneralSettings;
  alerts: AlertSettings;
  storage: StorageSettings;
  models: ModelSettings;
  privacy: PrivacySettings;
  system: SystemInfo;
}

export interface GeneralSettings {
  siteName: string;
  timezone: string;
  language: string;
}

export interface AlertSettings {
  emailNotifications: boolean;
  smsNotifications: boolean;
  pushNotifications: boolean;
  alertThreshold: Severity;
}

export interface StorageSettings {
  retentionDays: number;
  autoDelete: boolean;
  maxStorage: number;
}

export interface ModelSettings {
  detectionModel: string;
  confidenceThreshold: number;
  processingMode: 'realtime' | 'batch';
}

export interface PrivacySettings {
  maskFaces: boolean;
  anonymizeData: boolean;
  gdprCompliant: boolean;
}

export interface SystemInfo {
  version: string;
  build: string;
  uptime: string;
}

// WebSocket Event Types
export interface WebSocketEvent {
  type: 'incident' | 'camera_status' | 'system_alert' | 'metrics_update';
  payload: unknown;
  timestamp: string;
}

// API Response Types
export interface ApiResponse<T> {
  data: T;
  success: boolean;
  message?: string;
  error?: string;
}

export interface PaginatedResponse<T> {
  data: T[];
  total: number;
  page: number;
  pageSize: number;
  totalPages: number;
}

// Filter Types
export interface IncidentFilters {
  severity?: Severity | 'all';
  type?: IncidentType | 'all';
  status?: IncidentStatus | 'all';
  camera?: string | 'all';
  dateRange?: DateRange;
}

export interface DateRange {
  start: Date;
  end: Date;
}
