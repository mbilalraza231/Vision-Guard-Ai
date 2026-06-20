import type { Session } from '@supabase/supabase-js';

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
  session: Session | null;
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
  snapshotUrl?: string | null;
  clipUrl?: string | null;
  confidence?: number;
  incidentTime: string;
  reportingTime: string;
  processingDelay?: number;
  createdAt: string;
  updatedAt: string;
  acknowledgedBy?: string | null;
  acknowledgedAt?: string | null;
  resolvedBy?: string | null;
  resolvedAt?: string | null;
  resolution?: string | null;
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

// Zone from the backend API
export interface ZoneApiResponse {
  id: string;
  name: string;
  active_hours: string;
  max_cameras: number;
  max_alert_recipients: number;
  priority_weapon?: string;
  priority_fire?: string;
  priority_fall?: string;
  created_at: number;
}

export interface DetectionPriority {
  fire: Severity;
  weapon: Severity;
  fall: Severity;
}

// Alert Contact Types
export interface AlertContact {
  id: string;
  name: string;
  phone?: string;
  email?: string;
  whatsapp: boolean;
  email_alert: boolean;
  min_severity: string;
  is_active: boolean;
  zone_ids: string; // JSON array string e.g. '["zone-id-1"]'
  created_at: number;
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
  cameras: CameraSettings;
  workers: WorkerSettings;
  ecs: EcsSettings;
  cameraCapture: CameraCaptureSettings;
  clips: ClipSettings;
  alerts: AlertSettings;
  storage: StorageSettings;
  models: ModelSettings;
  privacy: PrivacySettings;
  system: SystemInfo;
  systemOverrides: SystemOverrides;
  notifications: NotificationSettings;
  queueManagement: QueueManagementSettings;
}

export interface CameraSettings {
  globalFpsTarget: number;
  targetLatencyMs: number;
  targetMemoryGb: number;
  targetFalsePositiveRate: number;
}

export interface WorkerSettings {
  thresholds: {
    weapon: number;
    fire: number;
    fall: number;
  };
  imageSaveThreshold: number;
  maxSnapshotBuffer?: number;
}

export interface EcsPersistenceSettings {
  minDetections: number;
  windowSec: number;
  cooldownSec: number;
}

export interface EcsSettings {
  thresholds: {
    weapon: number;
    fire: number;
    fall: number;
  };
  correlationWindowMs: number;
  hardTtlSeconds: number;
  enableAlerts: boolean;
  enableDatabase: boolean;
  enableFrontend: boolean;
  maxSourceLagSec: number;
  resumeFromLatest: boolean;
  weaponPersistence: EcsPersistenceSettings;
  firePersistence: EcsPersistenceSettings;
  fallPersistence: EcsPersistenceSettings;
}

export interface CameraCaptureSettings {
  defaultFps: number;
  motionThreshold: number;
  enableFrameCompression?: boolean;
  compressionQuality?: number;
  compressionFormat?: string;
  preResizeDimensions?: string;
}

export interface ClipSettings {
  preSeconds: number;
  postSeconds: number;
  fps: number;
  enableBackgroundBuffer: boolean;
}

export interface SystemOverrides {
  memoryTotalGbOverride: number;
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
  processingMode: 'realtime';
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

export interface NotificationSettings {
  recipients: Array<{
    id: string;
    name: string;
    phone: string;
    email: string;
    whatsapp: boolean;
    emailAlert: boolean;
    minSeverity: 'critical' | 'high' | 'medium' | 'low';
  }>;
}

export interface QueueManagementSettings {
  maxQueueSize: number;
  taskTtlSeconds: number;
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
  timePeriod?: string;
}

export interface DateRange {
  start: Date;
  end: Date;
}
