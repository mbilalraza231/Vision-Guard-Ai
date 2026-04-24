import { useMemo, useState } from 'react';
import { Header } from '@/components/layout/Header';
import { cn } from '@/lib/utils';
import { useQuery } from '@tanstack/react-query';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Switch } from '@/components/ui/switch';
import { Slider } from '@/components/ui/slider';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Loader2, RefreshCw, Save, RotateCcw } from 'lucide-react';
import { apiService } from '@/services/api.service';
import type {
  AlertSettings,
  GeneralSettings,
  ModelSettings,
  PrivacySettings,
  StorageSettings,
  SystemInfo,
  SystemSettings,
} from '@/types';

type SettingsTab = 'general' | 'alerts' | 'storage' | 'models' | 'privacy' | 'system';

interface TabItem {
  id: SettingsTab;
  label: string;
}

const tabs: TabItem[] = [
  { id: 'general', label: 'General' },
  { id: 'alerts', label: 'Alerts' },
  { id: 'storage', label: 'Storage' },
  { id: 'models', label: 'Models' },
  { id: 'privacy', label: 'Privacy' },
  { id: 'system', label: 'System' },
];

const SETTINGS_STORAGE_KEY = 'vg:dashboard:settings';

const defaultSettings: SystemSettings = {
  general: {
    siteName: 'VisionGuard AI',
    timezone: 'UTC',
    language: 'en',
  },
  alerts: {
    emailNotifications: true,
    smsNotifications: false,
    pushNotifications: true,
    alertThreshold: 'high',
  },
  storage: {
    retentionDays: 30,
    autoDelete: true,
    maxStorage: 50,
  },
  models: {
    detectionModel: 'yolo-edge-v2',
    confidenceThreshold: 0.7,
    processingMode: 'realtime',
  },
  privacy: {
    maskFaces: false,
    anonymizeData: true,
    gdprCompliant: true,
  },
  system: {
    version: '-',
    build: '-',
    uptime: '-',
  },
};

interface HealthResponse {
  status: string;
  timestamp: string;
  version: string;
}

interface StatusResponse {
  status: string;
  timestamp: string;
  uptime_seconds: number;
  components: Record<string, { name: string; status: string }>;
}

interface MetricsResponse {
  timestamp: string;
  system?: {
    uptime_seconds?: number;
    environment?: string;
    version?: string;
  };
  ecs?: {
    state?: string;
    uptime_seconds?: number;
    restart_count?: number;
  };
  cameras?: {
    total?: number;
    running?: number;
    stopped?: number;
  };
  redis?: {
    status?: string;
    version?: string;
  };
}

function formatDuration(seconds: number | undefined): string {
  if (!seconds || Number.isNaN(seconds)) return '-';
  const total = Math.floor(seconds);
  const days = Math.floor(total / 86400);
  const hours = Math.floor((total % 86400) / 3600);
  const minutes = Math.floor((total % 3600) / 60);
  if (days > 0) return `${days}d ${hours}h ${minutes}m`;
  if (hours > 0) return `${hours}h ${minutes}m`;
  return `${minutes}m`;
}

function readStoredSettings(): SystemSettings {
  const raw = localStorage.getItem(SETTINGS_STORAGE_KEY);
  if (!raw) {
    return defaultSettings;
  }
  try {
    const parsed = JSON.parse(raw) as Partial<SystemSettings>;
    return {
      ...defaultSettings,
      ...parsed,
      general: { ...defaultSettings.general, ...(parsed.general ?? {}) },
      alerts: { ...defaultSettings.alerts, ...(parsed.alerts ?? {}) },
      storage: { ...defaultSettings.storage, ...(parsed.storage ?? {}) },
      models: { ...defaultSettings.models, ...(parsed.models ?? {}) },
      privacy: { ...defaultSettings.privacy, ...(parsed.privacy ?? {}) },
      system: { ...defaultSettings.system, ...(parsed.system ?? {}) },
    };
  } catch {
    return defaultSettings;
  }
}

export default function Settings() {
  const [activeTab, setActiveTab] = useState<SettingsTab>('system');
  const [settings, setSettings] = useState<SystemSettings>(() => readStoredSettings());
  const [saveMessage, setSaveMessage] = useState<string>('');

  const {
    data: health,
    isLoading: healthLoading,
    error: healthError,
    refetch: refetchHealth,
  } = useQuery({
    queryKey: ['settings-health'],
    queryFn: () => apiService.getData<HealthResponse>('/health'),
    refetchInterval: 30000,
  });

  const {
    data: status,
    isLoading: statusLoading,
    error: statusError,
    refetch: refetchStatus,
  } = useQuery({
    queryKey: ['settings-status'],
    queryFn: () => apiService.getData<StatusResponse>('/status'),
    refetchInterval: 30000,
  });

  const {
    data: metrics,
    isLoading: metricsLoading,
    error: metricsError,
    refetch: refetchMetrics,
  } = useQuery({
    queryKey: ['settings-metrics'],
    queryFn: () => apiService.getData<MetricsResponse>('/metrics'),
    refetchInterval: 30000,
  });

  const isSystemLoading = healthLoading || statusLoading || metricsLoading;
  const hasSystemError = healthError || statusError || metricsError;

  const systemInfo: SystemInfo = useMemo(() => {
    return {
      version: metrics?.system?.version || health?.version || '-',
      build: status?.timestamp || '-',
      uptime: formatDuration(status?.uptime_seconds || metrics?.system?.uptime_seconds),
    };
  }, [health?.version, metrics?.system?.uptime_seconds, metrics?.system?.version, status?.timestamp, status?.uptime_seconds]);

  const persistSettings = (next: SystemSettings) => {
    localStorage.setItem(SETTINGS_STORAGE_KEY, JSON.stringify(next));
    setSettings(next);
    setSaveMessage('Settings saved successfully');
    setTimeout(() => setSaveMessage(''), 2500);
  };

  const resetSettings = () => {
    localStorage.setItem(SETTINGS_STORAGE_KEY, JSON.stringify(defaultSettings));
    setSettings(defaultSettings);
    setSaveMessage('Settings reset to defaults');
    setTimeout(() => setSaveMessage(''), 2500);
  };

  const updateGeneral = (patch: Partial<GeneralSettings>) => {
    setSettings((prev) => ({ ...prev, general: { ...prev.general, ...patch } }));
  };

  const updateAlerts = (patch: Partial<AlertSettings>) => {
    setSettings((prev) => ({ ...prev, alerts: { ...prev.alerts, ...patch } }));
  };

  const updateStorage = (patch: Partial<StorageSettings>) => {
    setSettings((prev) => ({ ...prev, storage: { ...prev.storage, ...patch } }));
  };

  const updateModels = (patch: Partial<ModelSettings>) => {
    setSettings((prev) => ({ ...prev, models: { ...prev.models, ...patch } }));
  };

  const updatePrivacy = (patch: Partial<PrivacySettings>) => {
    setSettings((prev) => ({ ...prev, privacy: { ...prev.privacy, ...patch } }));
  };

  return (
    <div className="min-h-screen">
      <Header title="Settings" showDateNav={false} />
      <div className="p-6">
        <div className="dashboard-card">
          <div className="flex flex-col md:flex-row">
            {/* Sidebar Navigation */}
            <div className="w-full md:w-48 border-b md:border-b-0 md:border-r border-border p-4">
              <nav className="flex md:flex-col gap-1 overflow-x-auto md:overflow-visible">
                {tabs.map((tab) => (
                  <button
                    key={tab.id}
                    onClick={() => setActiveTab(tab.id)}
                    className={cn(
                      'px-4 py-2 text-sm font-medium rounded-lg text-left whitespace-nowrap transition-colors',
                      activeTab === tab.id
                        ? 'bg-primary text-primary-foreground'
                        : 'text-muted-foreground hover:bg-secondary/50 hover:text-foreground'
                    )}
                  >
                    {tab.label}
                  </button>
                ))}
              </nav>
            </div>

            {/* Content Area */}
            <div className="flex-1 p-6">
              <div className="flex items-center justify-between mb-6 gap-3 flex-wrap">
                <div className="text-sm text-muted-foreground">
                  Changes are stored locally in this browser.
                </div>
                <div className="flex items-center gap-2">
                  <Button
                    variant="outline"
                    className="gap-2"
                    onClick={resetSettings}
                  >
                    <RotateCcw className="h-4 w-4" />
                    Reset
                  </Button>
                  <Button
                    className="gap-2"
                    onClick={() => persistSettings(settings)}
                  >
                    <Save className="h-4 w-4" />
                    Save
                  </Button>
                </div>
              </div>

              {saveMessage && (
                <div className="mb-6 rounded-lg border border-primary/30 bg-primary/10 px-4 py-3 text-sm text-primary">
                  {saveMessage}
                </div>
              )}

              {activeTab === 'system' && (
                <div className="animate-fade-in">
                  <h2 className="text-2xl font-bold mb-6">System Information</h2>
                  {isSystemLoading ? (
                    <div className="flex items-center gap-2 text-muted-foreground">
                      <Loader2 className="h-4 w-4 animate-spin" />
                      Loading backend system status...
                    </div>
                  ) : hasSystemError ? (
                    <div className="space-y-3">
                      <p className="text-severity-critical">Failed to load system status from backend.</p>
                      <Button
                        variant="outline"
                        className="gap-2"
                        onClick={() => {
                          refetchHealth();
                          refetchStatus();
                          refetchMetrics();
                        }}
                      >
                        <RefreshCw className="h-4 w-4" /> Retry
                      </Button>
                    </div>
                  ) : (
                    <>
                      <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6">
                        <div className="rounded-xl bg-secondary/30 p-4">
                          <p className="text-sm text-muted-foreground mb-1">Version</p>
                          <p className="text-xl font-semibold">{systemInfo.version}</p>
                        </div>
                        <div className="rounded-xl bg-secondary/30 p-4">
                          <p className="text-sm text-muted-foreground mb-1">Build Timestamp</p>
                          <p className="text-sm font-semibold break-words">{systemInfo.build}</p>
                        </div>
                        <div className="rounded-xl bg-secondary/30 p-4">
                          <p className="text-sm text-muted-foreground mb-1">Uptime</p>
                          <p className="text-xl font-semibold">{systemInfo.uptime}</p>
                        </div>
                      </div>

                      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                        <div className="rounded-xl bg-secondary/30 p-4">
                          <p className="text-sm text-muted-foreground mb-2">Overall Status</p>
                          <p className="font-semibold capitalize">{status?.status ?? '-'}</p>
                        </div>
                        <div className="rounded-xl bg-secondary/30 p-4">
                          <p className="text-sm text-muted-foreground mb-2">Environment</p>
                          <p className="font-semibold">{metrics?.system?.environment ?? '-'}</p>
                        </div>
                        <div className="rounded-xl bg-secondary/30 p-4">
                          <p className="text-sm text-muted-foreground mb-2">ECS State</p>
                          <p className="font-semibold">{metrics?.ecs?.state ?? '-'}</p>
                        </div>
                        <div className="rounded-xl bg-secondary/30 p-4">
                          <p className="text-sm text-muted-foreground mb-2">Redis</p>
                          <p className="font-semibold">{metrics?.redis?.status ?? '-'}</p>
                        </div>
                      </div>
                    </>
                  )}
                </div>
              )}

              {activeTab === 'general' && (
                <div className="animate-fade-in">
                  <h2 className="text-2xl font-bold mb-6">General Settings</h2>
                  <div className="space-y-5 max-w-xl">
                    <div className="space-y-2">
                      <Label htmlFor="siteName">Site Name</Label>
                      <Input
                        id="siteName"
                        value={settings.general.siteName}
                        onChange={(e) => updateGeneral({ siteName: e.target.value })}
                      />
                    </div>

                    <div className="space-y-2">
                      <Label>Timezone</Label>
                      <Select
                        value={settings.general.timezone}
                        onValueChange={(value) => updateGeneral({ timezone: value })}
                      >
                        <SelectTrigger>
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="UTC">UTC</SelectItem>
                          <SelectItem value="Asia/Karachi">Asia/Karachi</SelectItem>
                          <SelectItem value="Asia/Dubai">Asia/Dubai</SelectItem>
                          <SelectItem value="Europe/London">Europe/London</SelectItem>
                          <SelectItem value="America/New_York">America/New_York</SelectItem>
                        </SelectContent>
                      </Select>
                    </div>

                    <div className="space-y-2">
                      <Label>Language</Label>
                      <Select
                        value={settings.general.language}
                        onValueChange={(value) => updateGeneral({ language: value })}
                      >
                        <SelectTrigger>
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="en">English</SelectItem>
                          <SelectItem value="ur">Urdu</SelectItem>
                          <SelectItem value="ar">Arabic</SelectItem>
                        </SelectContent>
                      </Select>
                    </div>
                  </div>
                </div>
              )}

              {activeTab === 'alerts' && (
                <div className="animate-fade-in">
                  <h2 className="text-2xl font-bold mb-6">Alert Settings</h2>
                  <div className="space-y-5 max-w-xl">
                    <div className="flex items-center justify-between rounded-lg bg-secondary/30 px-4 py-3">
                      <Label htmlFor="emailNotifications">Email Notifications</Label>
                      <Switch
                        id="emailNotifications"
                        checked={settings.alerts.emailNotifications}
                        onCheckedChange={(checked) => updateAlerts({ emailNotifications: checked })}
                      />
                    </div>

                    <div className="flex items-center justify-between rounded-lg bg-secondary/30 px-4 py-3">
                      <Label htmlFor="smsNotifications">SMS Notifications</Label>
                      <Switch
                        id="smsNotifications"
                        checked={settings.alerts.smsNotifications}
                        onCheckedChange={(checked) => updateAlerts({ smsNotifications: checked })}
                      />
                    </div>

                    <div className="flex items-center justify-between rounded-lg bg-secondary/30 px-4 py-3">
                      <Label htmlFor="pushNotifications">Push Notifications</Label>
                      <Switch
                        id="pushNotifications"
                        checked={settings.alerts.pushNotifications}
                        onCheckedChange={(checked) => updateAlerts({ pushNotifications: checked })}
                      />
                    </div>

                    <div className="space-y-2">
                      <Label>Alert Severity Threshold</Label>
                      <Select
                        value={settings.alerts.alertThreshold}
                        onValueChange={(value) => updateAlerts({ alertThreshold: value as AlertSettings['alertThreshold'] })}
                      >
                        <SelectTrigger>
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="critical">Critical</SelectItem>
                          <SelectItem value="high">High</SelectItem>
                          <SelectItem value="medium">Medium</SelectItem>
                          <SelectItem value="low">Low</SelectItem>
                        </SelectContent>
                      </Select>
                    </div>
                  </div>
                </div>
              )}

              {activeTab === 'storage' && (
                <div className="animate-fade-in">
                  <h2 className="text-2xl font-bold mb-6">Storage Settings</h2>
                  <div className="space-y-5 max-w-xl">
                    <div className="space-y-2">
                      <Label htmlFor="retentionDays">Retention Days</Label>
                      <Input
                        id="retentionDays"
                        type="number"
                        min={1}
                        max={365}
                        value={settings.storage.retentionDays}
                        onChange={(e) =>
                          updateStorage({
                            retentionDays: Math.max(1, Math.min(365, Number(e.target.value) || 1)),
                          })
                        }
                      />
                    </div>

                    <div className="space-y-2">
                      <Label htmlFor="maxStorage">Max Storage (GB)</Label>
                      <Input
                        id="maxStorage"
                        type="number"
                        min={1}
                        max={2000}
                        value={settings.storage.maxStorage}
                        onChange={(e) =>
                          updateStorage({
                            maxStorage: Math.max(1, Math.min(2000, Number(e.target.value) || 1)),
                          })
                        }
                      />
                    </div>

                    <div className="flex items-center justify-between rounded-lg bg-secondary/30 px-4 py-3">
                      <Label htmlFor="autoDelete">Auto-delete old data</Label>
                      <Switch
                        id="autoDelete"
                        checked={settings.storage.autoDelete}
                        onCheckedChange={(checked) => updateStorage({ autoDelete: checked })}
                      />
                    </div>
                  </div>
                </div>
              )}

              {activeTab === 'models' && (
                <div className="animate-fade-in">
                  <h2 className="text-2xl font-bold mb-6">AI Model Settings</h2>
                  <div className="space-y-5 max-w-xl">
                    <div className="space-y-2">
                      <Label>Detection Model</Label>
                      <Select
                        value={settings.models.detectionModel}
                        onValueChange={(value) => updateModels({ detectionModel: value })}
                      >
                        <SelectTrigger>
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="yolo-edge-v2">YOLO Edge v2</SelectItem>
                          <SelectItem value="yolo-fast-v1">YOLO Fast v1</SelectItem>
                          <SelectItem value="openvino-fire-int8">OpenVINO Fire INT8</SelectItem>
                        </SelectContent>
                      </Select>
                    </div>

                    <div className="space-y-3">
                      <Label>Confidence Threshold ({(settings.models.confidenceThreshold * 100).toFixed(0)}%)</Label>
                      <Slider
                        value={[settings.models.confidenceThreshold * 100]}
                        min={10}
                        max={99}
                        step={1}
                        onValueChange={(value) => updateModels({ confidenceThreshold: value[0] / 100 })}
                      />
                    </div>

                    <div className="space-y-2">
                      <Label>Processing Mode</Label>
                      <Select
                        value={settings.models.processingMode}
                        onValueChange={(value) => updateModels({ processingMode: value as ModelSettings['processingMode'] })}
                      >
                        <SelectTrigger>
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="realtime">Realtime</SelectItem>
                          <SelectItem value="batch">Batch</SelectItem>
                        </SelectContent>
                      </Select>
                    </div>
                  </div>
                </div>
              )}

              {activeTab === 'privacy' && (
                <div className="animate-fade-in">
                  <h2 className="text-2xl font-bold mb-6">Privacy Settings</h2>
                  <div className="space-y-5 max-w-xl">
                    <div className="flex items-center justify-between rounded-lg bg-secondary/30 px-4 py-3">
                      <Label htmlFor="maskFaces">Mask Faces</Label>
                      <Switch
                        id="maskFaces"
                        checked={settings.privacy.maskFaces}
                        onCheckedChange={(checked) => updatePrivacy({ maskFaces: checked })}
                      />
                    </div>

                    <div className="flex items-center justify-between rounded-lg bg-secondary/30 px-4 py-3">
                      <Label htmlFor="anonymizeData">Anonymize Data</Label>
                      <Switch
                        id="anonymizeData"
                        checked={settings.privacy.anonymizeData}
                        onCheckedChange={(checked) => updatePrivacy({ anonymizeData: checked })}
                      />
                    </div>

                    <div className="flex items-center justify-between rounded-lg bg-secondary/30 px-4 py-3">
                      <Label htmlFor="gdprCompliant">GDPR Compliance Mode</Label>
                      <Switch
                        id="gdprCompliant"
                        checked={settings.privacy.gdprCompliant}
                        onCheckedChange={(checked) => updatePrivacy({ gdprCompliant: checked })}
                      />
                    </div>
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
