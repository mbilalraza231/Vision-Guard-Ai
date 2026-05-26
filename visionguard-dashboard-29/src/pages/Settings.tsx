import { useMemo, useState, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { Header } from '@/components/layout/Header';
import { useSettings } from '@/hooks/useSettings';
import { cn } from '@/lib/utils';
import { useQuery, useQueryClient } from '@tanstack/react-query';
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
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from '@/components/ui/dialog';
import { Loader2, RefreshCw, Save, RotateCcw, Bell, ShieldCheck, Mail, Phone, Plus, Trash2 } from 'lucide-react';
import { apiService } from '@/services/api.service';
import { buildApiUrl } from '@/config/api';
import { formatTimeString } from '@/lib/utils';
import type {
  AlertSettings,
  GeneralSettings,
  ModelSettings,
  PrivacySettings,
  StorageSettings,
  SystemInfo,
  SystemSettings,
} from '@/types';

type SettingsTab = 'general' | 'alerts' | 'notifications' | 'storage' | 'models' | 'privacy' | 'system';

interface TabItem {
  id: SettingsTab;
  label: string;
}

const tabs: TabItem[] = [
  { id: 'general', label: 'General' },
  { id: 'alerts', label: 'Alert Rules' },
  { id: 'notifications', label: 'Notifications' },
  { id: 'storage', label: 'Storage' },
  { id: 'models', label: 'Models' },
  { id: 'privacy', label: 'Privacy' },
  { id: 'system', label: 'System' },
];

// Settings are now persisted in PostgreSQL via /api/v1/settings

const defaultSettings: SystemSettings = {
  general: {
    siteName: 'VisionGuard AI',
    timezone: 'Asia/Karachi',
    language: 'en',
  },
  alerts: {
    emailNotifications: false,
    smsNotifications: false,
    pushNotifications: false,
    alertThreshold: 'low',
  },
  storage: {
    retentionDays: 30,
    autoDelete: false,
    maxStorage: 50,
  },
  models: {
    detectionModel: 'yolo-edge-v2',
    confidenceThreshold: 0.7,
    processingMode: 'realtime',
  },
  privacy: {
    maskFaces: false,
    anonymizeData: false,
    gdprCompliant: false,
  },
  system: {
    version: '-',
    build: '-',
    uptime: '-',
  },
  notifications: {
    recipients: [],
    twilio: { sid: '', token: '', from: '' },
    gmail: { server: 'smtp.gmail.com', user: '', pass: '' }
  }
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
  workers?: Array<{
    name: string;
    instance: string;
    cpu: number;
    memory: number;
    last_seen: number;
    status: 'online' | 'offline';
  }>;
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

// Settings are fetched from the backend API on mount

export default function Settings() {
  const { t, i18n } = useTranslation();
  const [activeTab, setActiveTab] = useState<SettingsTab>('system');
  const [settings, setSettings] = useState<SystemSettings>(defaultSettings);
  const [saveMessage, setSaveMessage] = useState<string>('');
  const [settingsLoading, setSettingsLoading] = useState(true);

  // Fetch settings from backend API on mount
  useEffect(() => {
    let cancelled = false;
    const fetchSettings = async () => {
      try {
        const data = await apiService.getData<SystemSettings>('/api/v1/settings');
        if (!cancelled) {
          setSettings((prev: SystemSettings) => ({
            ...prev,
            ...data,
            system: prev.system, // system info comes from /health, /status, /metrics
          }));
          // Sync i18n with loaded setting
          if (data?.general?.language) {
            i18n.changeLanguage(data.general.language);
          }
        }
      } catch (err) {
        console.warn('Failed to fetch settings from API, using defaults', err);
      } finally {
        if (!cancelled) setSettingsLoading(false);
      }
    };
    fetchSettings();
    return () => { cancelled = true; };
  }, []);

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
  });

  const {
    data: metrics,
    isLoading: metricsLoading,
    error: metricsError,
    refetch: refetchMetrics,
  } = useQuery({
    queryKey: ['settings-metrics'],
    queryFn: () => apiService.getData<MetricsResponse>('/metrics'),
  });

  const queryClient = useQueryClient();

  useEffect(() => {
    const sseUrl = buildApiUrl('/stream');
    const eventSource = new EventSource(sseUrl);

    eventSource.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        if (data.status) {
          queryClient.setQueryData(['settings-status'], data.status);
        }
        if (data.metrics) {
          queryClient.setQueryData(['settings-metrics'], data.metrics);
        }
      } catch (err) {
        console.error("SSE parse error", err);
      }
    };

    eventSource.onerror = (error) => {
      console.error("SSE Connection Error", error);
      eventSource.close();
    };

    return () => {
      eventSource.close();
    };
  }, [queryClient]);

  const isSystemLoading = healthLoading || statusLoading || metricsLoading;
  const hasSystemError = healthError || statusError || metricsError;

  const systemInfo: SystemInfo = useMemo(() => {
    return {
      version: metrics?.system?.version || health?.version || '-',
      build: status?.timestamp || '-',
      uptime: formatDuration(status?.uptime_seconds || metrics?.system?.uptime_seconds),
    };
  }, [health?.version, metrics?.system?.uptime_seconds, metrics?.system?.version, status?.timestamp, status?.uptime_seconds]);

  const persistSettings = async (next: SystemSettings) => {
    try {
      const { general, alerts, storage, models, privacy, notifications } = next;
      const saved = await apiService.putData<SystemSettings>('/api/v1/settings', { general, alerts, storage, models, privacy, notifications });
      setSettings((prev: SystemSettings) => ({ ...prev, ...saved }));
      setSaveMessage(t('settings.buttons.save') + ' Successful');
      i18n.changeLanguage(saved.general.language);
      queryClient.setQueryData(['system-settings'], saved);
      // Also persist to localStorage so timezone/siteName are instant on next render
      try { localStorage.setItem('vg:settings:cache', JSON.stringify(saved)); } catch {}
    } catch (err) {
      console.error('Failed to save settings', err);
      setSaveMessage('Failed to save settings');
    }
    setTimeout(() => setSaveMessage(''), 2500);
  };

  const resetSettings = async () => {
    try {
      const defaults = await apiService.postData<SystemSettings>('/api/v1/settings/reset');
      
      // Override backend defaults with our new UI defaults
      defaults.general.timezone = 'Asia/Karachi';
      defaults.general.siteName = 'VisionGuard AI';
      
      // Persist these overridden defaults back to the backend immediately
      await apiService.putData<SystemSettings>('/api/v1/settings', defaults);
      
      setSettings((prev: SystemSettings) => ({ ...prev, ...defaults }));
      setSaveMessage(t('settings.buttons.reset') + ' Successful');
      i18n.changeLanguage(defaults.general.language);
      queryClient.setQueryData(['system-settings'], defaults);
      // Also persist to localStorage so timezone/siteName are instant on next render
      try { localStorage.setItem('vg:settings:cache', JSON.stringify(defaults)); } catch {}
    } catch (err) {
      console.error('Failed to reset settings', err);
      setSaveMessage('Failed to reset settings');
    }
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
    setSettings((prev: SystemSettings) => ({ ...prev, privacy: { ...prev.privacy, ...patch } }));
  };

  const updateTwilio = (patch: Partial<SystemSettings['notifications']['twilio']>) => {
    setSettings((prev: SystemSettings) => ({ 
      ...prev, 
      notifications: { ...prev.notifications, twilio: { ...prev.notifications.twilio, ...patch } } 
    }));
  };

  const updateGmail = (patch: Partial<SystemSettings['notifications']['gmail']>) => {
    setSettings((prev: SystemSettings) => ({ 
      ...prev, 
      notifications: { ...prev.notifications, gmail: { ...prev.notifications.gmail, ...patch } } 
    }));
  };

  return (
    <div className="min-h-screen">
      <Header title={t('settings.title', 'Settings')} showDateNav={false} />
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
                    {t(`settings.tabs.${tab.id}`, tab.label)}
                  </button>
                ))}
              </nav>
            </div>

            {/* Content Area */}
            <div className="flex-1 p-6">
              <div className="flex items-center justify-between mb-6 gap-3 flex-wrap">
                <div className="text-sm text-muted-foreground">
                  {t('settings.syncedMessage', 'Settings are synced with the VisionGuard backend.')}
                </div>
                <div className="flex items-center gap-2">
                  <Button
                    variant="outline"
                    className="gap-2"
                    onClick={resetSettings}
                  >
                    <RotateCcw className="h-4 w-4" />
                    {t('settings.buttons.reset', 'Reset')}
                  </Button>
                  <Button
                    className="gap-2"
                    onClick={() => persistSettings(settings)}
                  >
                    <Save className="h-4 w-4" />
                    {t('settings.buttons.save', 'Save')}
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

                      {/* AI Workers Heartbeats */}
                      <div className="mt-8">
                        <h3 className="text-lg font-bold mb-4 flex items-center gap-2">
                          <ShieldCheck className="h-5 w-5 text-primary" />
                          AI Worker Heartbeats
                        </h3>
                        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                          {metrics?.workers?.map((w) => (
                            <div key={w.name + w.instance} className="rounded-xl border border-white/5 bg-secondary/20 p-4">
                              <div className="flex items-center justify-between mb-3">
                                <span className="font-bold capitalize">{w.name.replace('_', ' ')}</span>
                                <div className={cn(
                                  "flex items-center gap-1.5 px-2 py-0.5 rounded-full text-[10px] font-bold uppercase",
                                  w.status === 'online' ? "bg-status-online/10 text-status-online" : "bg-severity-critical/10 text-severity-critical"
                                )}>
                                  <div className={cn("h-1.5 w-1.5 rounded-full animate-pulse", w.status === 'online' ? "bg-status-online" : "bg-severity-critical")} />
                                  {w.status}
                                </div>
                              </div>
                              <div className="space-y-1 text-xs text-muted-foreground">
                                <div className="flex justify-between">
                                  <span>Instance</span>
                                  <span className="font-mono">{w.instance.slice(0, 12)}</span>
                                </div>
                                <div className="flex justify-between">
                                  <span>CPU Usage</span>
                                  <span>{w.cpu}%</span>
                                </div>
                                <div className="flex justify-between">
                                  <span>Memory</span>
                                  <span>{(w.memory * 1024).toFixed(0)} MB</span>
                                </div>
                                <div className="flex justify-between pt-1 border-t border-white/5 mt-1">
                                  <span>Last Seen</span>
                                  <span>{formatTimeString(w.last_seen * 1000, settings.general.timezone)}</span>
                                </div>
                              </div>
                            </div>
                          ))}
                          {(!metrics?.workers || metrics.workers.length === 0) && (
                            <div className="col-span-full py-8 text-center rounded-xl border border-dashed border-white/10 text-muted-foreground text-sm">
                              No AI workers detected in the last 60 seconds.
                            </div>
                          )}
                        </div>
                      </div>
                    </>
                  )}
                </div>
              )}

              {activeTab === 'general' && (
                <div className="animate-fade-in">
                  <h2 className="text-2xl font-bold mb-6">{t('settings.tabs.general', 'General Settings')}</h2>
                  <div className="space-y-5 max-w-xl">
                    <div className="space-y-2">
                      <Label htmlFor="siteName">{t('settings.general.siteName', 'Site Name')}</Label>
                      <Input
                        id="siteName"
                        value={settings.general.siteName}
                        onChange={(e) => updateGeneral({ siteName: e.target.value })}
                      />
                    </div>

                    <div className="space-y-2">
                      <Label>{t('settings.general.timezone', 'Timezone')}</Label>
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
                      <Label>{t('settings.general.language', 'Language')}</Label>
                      <Select
                        value={settings.general.language}
                        onValueChange={(value) => updateGeneral({ language: value })}
                      >
                        <SelectTrigger>
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="en">{t('settings.general.english', 'English')}</SelectItem>
                          <SelectItem value="es">{t('settings.general.spanish', 'Spanish')}</SelectItem>
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
                        value={settings.models.processingMode || 'realtime'}
                        onValueChange={(value) => updateModels({ processingMode: value as any })}
                      >
                        <SelectTrigger>
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="realtime">Realtime</SelectItem>
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

              {activeTab === 'notifications' && (
                <div className="animate-fade-in space-y-8">
                  <div className="pt-2">
                    <h2 className="text-xl font-bold mb-6 flex items-center gap-2">
                      <ShieldCheck className="h-5 w-5 text-primary" />
                      Alert Credentials
                    </h2>
                    
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
                      {/* Twilio Config */}
                      <div className="space-y-4 rounded-xl border border-white/5 bg-secondary/10 p-5">
                        <div className="flex items-center gap-2 font-semibold text-status-online">
                          Twilio (WhatsApp)
                        </div>
                        <div className="space-y-3">
                          <div className="space-y-1.5">
                            <Label className="text-xs text-muted-foreground">Account SID</Label>
                            <Input 
                              placeholder="ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx" 
                              className="bg-background/50" 
                              value={settings.notifications.twilio.sid}
                              onChange={(e) => updateTwilio({ sid: e.target.value })}
                            />
                          </div>
                          <div className="space-y-1.5">
                            <Label className="text-xs text-muted-foreground">Auth Token</Label>
                            <Input 
                              type="password" 
                              placeholder="••••••••••••••••••••••••••••••••" 
                              className="bg-background/50" 
                              value={settings.notifications.twilio.token}
                              onChange={(e) => updateTwilio({ token: e.target.value })}
                            />
                          </div>
                          <div className="space-y-1.5">
                            <Label className="text-xs text-muted-foreground">From Number</Label>
                            <Input 
                              placeholder="whatsapp:+14155238886" 
                              className="bg-background/50" 
                              value={settings.notifications.twilio.from}
                              onChange={(e) => updateTwilio({ from: e.target.value })}
                            />
                          </div>
                        </div>
                      </div>

                      {/* Gmail Config */}
                      <div className="space-y-4 rounded-xl border border-white/5 bg-secondary/10 p-5">
                        <div className="flex items-center gap-2 font-semibold text-primary">
                          Gmail (SMTP)
                        </div>
                        <div className="space-y-3">
                          <div className="space-y-1.5">
                            <Label className="text-xs text-muted-foreground">SMTP Server</Label>
                            <Input 
                              className="bg-background/50" 
                              value={settings.notifications.gmail.server}
                              onChange={(e) => updateGmail({ server: e.target.value })}
                            />
                          </div>
                          <div className="space-y-1.5">
                            <Label className="text-xs text-muted-foreground">Sender Email</Label>
                            <Input 
                              placeholder="your-email@gmail.com" 
                              className="bg-background/50" 
                              value={settings.notifications.gmail.user}
                              onChange={(e) => updateGmail({ user: e.target.value })}
                            />
                          </div>
                          <div className="space-y-1.5">
                            <Label className="text-xs text-muted-foreground">App Password</Label>
                            <Input 
                              type="password" 
                              placeholder="xxxx xxxx xxxx xxxx" 
                              className="bg-background/50" 
                              value={settings.notifications.gmail.pass}
                              onChange={(e) => updateGmail({ pass: e.target.value })}
                            />
                          </div>
                        </div>
                      </div>
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
