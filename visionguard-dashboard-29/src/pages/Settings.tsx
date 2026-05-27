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
import { Loader2, RefreshCw, Save, RotateCcw, Bell, ShieldCheck, Mail, Phone, Plus, Trash2, Download, FileJson, Camera } from 'lucide-react';
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

type SettingsTab = 'general' | 'alerts' | 'notifications' | 'cameras' | 'storage' | 'models' | 'privacy' | 'system';

interface TabItem {
  id: SettingsTab;
  label: string;
}

const tabs: TabItem[] = [
  { id: 'general', label: 'General' },
  { id: 'alerts', label: 'Alert Rules' },
  { id: 'notifications', label: 'Notifications' },
  { id: 'cameras', label: 'Camera Rules' },
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
  cameras: {
    globalFpsTarget: 15,
    targetLatencyMs: 500,
    targetMemoryGb: 8.0,
    targetFalsePositiveRate: 5,
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
  memory_total_gb?: number;
  memory_used_gb?: number;
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

  // Clear save messages when changing tabs
  useEffect(() => {
    setSaveMessage('');
  }, [activeTab]);

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

  const persistSettings = async () => {
    try {
      const payload: Partial<SystemSettings> = {};
      if (activeTab === 'general') payload.general = settings.general;
      else if (activeTab === 'alerts') payload.alerts = settings.alerts;
      else if (activeTab === 'storage') payload.storage = settings.storage;
      else if (activeTab === 'models') payload.models = settings.models;
      else if (activeTab === 'cameras') payload.cameras = settings.cameras;
      else if (activeTab === 'privacy') payload.privacy = settings.privacy;
      else if (activeTab === 'notifications') payload.notifications = settings.notifications;
      else return; // 'system' tab has no settings

      const saved = await apiService.putData<SystemSettings>('/api/v1/settings', payload);
      setSettings((prev: SystemSettings) => ({ ...prev, ...saved }));
      const tabName = activeTab.charAt(0).toUpperCase() + activeTab.slice(1);
      setSaveMessage(`Save ${tabName} settings Successful`);
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

  const [exportingData, setExportingData] = useState(false);

  const handleGdprExport = async () => {
    setExportingData(true);
    setSaveMessage('Preparing GDPR Portable Data Profile...');
    try {
      const data = await apiService.getData<any>('/api/v1/settings/gdpr/export');
      const dataStr = "data:text/json;charset=utf-8," + encodeURIComponent(JSON.stringify(data, null, 2));
      const downloadAnchor = document.createElement('a');
      downloadAnchor.setAttribute("href", dataStr);
      downloadAnchor.setAttribute("download", "visionguard_gdpr_export.json");
      document.body.appendChild(downloadAnchor);
      downloadAnchor.click();
      downloadAnchor.remove();
      setSaveMessage('GDPR Data Profile downloaded successfully!');
    } catch (err) {
      console.error('Failed to export GDPR data', err);
      setSaveMessage('Failed to compile GDPR data export');
    } finally {
      setExportingData(false);
      setTimeout(() => setSaveMessage(''), 3000);
    }
  };

  const resetSettings = async () => {
    try {
      // Fetch pure defaults without modifying the DB
      const defaults = await apiService.getData<SystemSettings>('/api/v1/settings/defaults');
      
      // Override general defaults with our new UI defaults if resetting general
      if (activeTab === 'general') {
        defaults.general.timezone = 'Asia/Karachi';
        defaults.general.siteName = 'VisionGuard AI';
      }
      
      const payload: Partial<SystemSettings> = {};
      if (activeTab === 'general') payload.general = defaults.general;
      else if (activeTab === 'alerts') payload.alerts = defaults.alerts;
      else if (activeTab === 'storage') payload.storage = defaults.storage;
      else if (activeTab === 'models') payload.models = defaults.models;
      else if (activeTab === 'cameras') payload.cameras = defaults.cameras;
      else if (activeTab === 'privacy') payload.privacy = defaults.privacy;
      else if (activeTab === 'notifications') payload.notifications = defaults.notifications;
      else return; // 'system' tab has no settings
      
      // Persist ONLY the active tab's defaults back to the backend
      const saved = await apiService.putData<SystemSettings>('/api/v1/settings', payload);
      
      setSettings((prev: SystemSettings) => ({ ...prev, ...saved }));
      const tabName = activeTab.charAt(0).toUpperCase() + activeTab.slice(1);
      setSaveMessage(`Reset ${tabName} settings Successful`);
      i18n.changeLanguage(saved.general.language);
      queryClient.setQueryData(['system-settings'], saved);
      // Also persist to localStorage so timezone/siteName are instant on next render
      try { localStorage.setItem('vg:settings:cache', JSON.stringify(saved)); } catch {}
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

  const updateCameras = (patch: Partial<SystemSettings['cameras']>) => {
    setSettings((prev: SystemSettings) => ({ ...prev, cameras: { ...prev.cameras, ...patch } }));
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
    <div className="flex flex-col" style={{ height: 'calc(100vh - 64px)' }}>
      <Header title={t('settings.title', 'Settings')} showDateNav={false} />
      <div className="p-6 flex-1 overflow-hidden flex flex-col">
        <div className="dashboard-card flex flex-col flex-1 overflow-hidden">
          <div className="flex flex-col md:flex-row flex-1 overflow-hidden">
            {/* Sidebar Navigation – fixed in place, never scrolls */}
            <div className="w-full md:w-48 border-b md:border-b-0 md:border-r border-border p-4 shrink-0">
              <nav className="flex md:flex-col gap-1.5 overflow-x-auto md:overflow-visible">
                {tabs.map((tab) => (
                  <button
                    key={tab.id}
                    onClick={() => setActiveTab(tab.id)}
                    className={cn(
                      'px-4 py-2.5 text-sm font-medium rounded-lg text-left whitespace-nowrap transition-colors duration-150',
                      activeTab === tab.id
                        ? 'bg-primary text-primary-foreground font-semibold'
                        : 'text-muted-foreground hover:bg-secondary/30 hover:text-foreground'
                    )}
                  >
                    {t(`settings.tabs.${tab.id}`, tab.label)}
                  </button>
                ))}
              </nav>
            </div>

            {/* Content Area – only this scrolls */}
            <div className="flex-1 overflow-y-auto min-h-0">
              <div className="sticky top-0 z-20 bg-card px-6 pt-4 pb-4 border-b border-border/40 flex items-center justify-between gap-3 flex-wrap">
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
                    onClick={persistSettings}
                  >
                    <Save className="h-4 w-4" />
                    {t('settings.buttons.save', 'Save')}
                  </Button>
                </div>
              </div>

              <div className="px-6 pb-6">
                {saveMessage && (
                  <div className="mt-4 mb-4 rounded-lg border border-primary/30 bg-primary/10 px-4 py-3 text-sm text-primary">
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

                    {/* SMS Notifications disabled for now as it's not fully implemented */}
                    {/*
                    <div className="flex items-center justify-between rounded-lg bg-secondary/30 px-4 py-3">
                      <Label htmlFor="smsNotifications">SMS Notifications</Label>
                      <Switch
                        id="smsNotifications"
                        checked={settings.alerts.smsNotifications}
                        onCheckedChange={(checked) => updateAlerts({ smsNotifications: checked })}
                      />
                    </div>
                    */}

                    <div className="flex items-center justify-between rounded-lg bg-secondary/30 px-4 py-3">
                      <Label htmlFor="pushNotifications">WhatsApp Notifications</Label>
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
                      <div className="space-y-0.5">
                        <Label htmlFor="autoDelete">Enable Scheduled Cleanup</Label>
                        <p className="text-xs text-muted-foreground">
                          Master switch. When ON, the system runs a hourly cleanup job that enforces the Retention Days and Max Storage limits above.
                        </p>
                      </div>
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
                <div className="animate-fade-in space-y-6">
                  <div>
                    <h2 className="text-2xl font-bold mb-1 flex items-center gap-2">
                      <ShieldCheck className="h-6 w-6 text-primary" />
                      Privacy Settings
                    </h2>
                    <p className="text-sm text-muted-foreground">
                      Configure data protection, obfuscation levels, and GDPR regulatory compliance.
                    </p>
                  </div>

                  <div className="space-y-4 max-w-xl">
                    {/* Mask Faces */}
                    <div className="flex items-start justify-between rounded-xl border border-white/5 bg-secondary/10 p-5 transition-all hover:bg-secondary/20">
                      <div className="space-y-1">
                        <Label htmlFor="maskFaces" className="text-base font-semibold cursor-pointer">Mask Faces</Label>
                        <p className="text-xs text-muted-foreground max-w-sm">
                          Automatically blurs and covers detected faces in all saved snapshot evidence and stitched video clips before storage.
                        </p>
                      </div>
                      <Switch
                        id="maskFaces"
                        checked={settings.privacy.maskFaces}
                        onCheckedChange={(checked) => updatePrivacy({ maskFaces: checked })}
                      />
                    </div>

                    {/* Anonymize Data */}
                    <div className="flex items-start justify-between rounded-xl border border-white/5 bg-secondary/10 p-5 transition-all hover:bg-secondary/20">
                      <div className="space-y-1">
                        <Label htmlFor="anonymizeData" className="text-base font-semibold cursor-pointer">Anonymize Data</Label>
                        <p className="text-xs text-muted-foreground max-w-sm">
                          Obfuscates camera names and masks recipient contact details (phone numbers and emails) in the event database, notification logs, and alerts.
                        </p>
                      </div>
                      <Switch
                        id="anonymizeData"
                        checked={settings.privacy.anonymizeData}
                        onCheckedChange={(checked) => updatePrivacy({ anonymizeData: checked })}
                      />
                    </div>

                    {/* GDPR Compliance */}
                    <div className="flex items-start justify-between rounded-xl border border-white/5 bg-secondary/10 p-5 transition-all hover:bg-secondary/20">
                      <div className="space-y-1">
                        <Label htmlFor="gdprCompliant" className="text-base font-semibold cursor-pointer">GDPR Compliance Mode</Label>
                        <p className="text-xs text-muted-foreground max-w-sm">
                          Enforces strict right-to-be-forgotten and caps the data retention policy at a maximum of 30 days, actively auto-deleting old data automatically.
                        </p>
                      </div>
                      <Switch
                        id="gdprCompliant"
                        checked={settings.privacy.gdprCompliant}
                        onCheckedChange={(checked) => updatePrivacy({ gdprCompliant: checked })}
                      />
                    </div>
                  </div>

                  {/* GDPR Data Portability Audit Section */}
                  <div className="pt-6 max-w-xl border-t border-white/5">
                    <div className="rounded-xl border border-primary/20 bg-primary/5 p-5">
                      <h3 className="text-lg font-semibold text-primary mb-2 flex items-center gap-2">
                        <FileJson className="h-5 w-5" />
                        Right to Data Portability (GDPR Article 20)
                      </h3>
                      <p className="text-xs text-muted-foreground mb-4">
                        Download a secure, standardized JSON profile of your active security configurations, alert contacts, camera records, and incident histories.
                      </p>
                      <Button
                        onClick={handleGdprExport}
                        disabled={exportingData}
                        className="gap-2 bg-primary hover:bg-primary/90 text-primary-foreground font-semibold"
                      >
                        {exportingData ? (
                          <>
                            <Loader2 className="h-4 w-4 animate-spin" />
                            Compiling Data Export...
                          </>
                        ) : (
                          <>
                            <Download className="h-4 w-4" />
                            Export Portable Data Profile
                          </>
                        )}
                      </Button>
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

              {activeTab === 'cameras' && (
                <div className="animate-fade-in space-y-6">
                  <div>
                    <h2 className="text-2xl font-bold mb-1 flex items-center gap-2">
                      <Camera className="h-6 w-6 text-primary" />
                      Camera Rules & Performance
                    </h2>
                    <p className="text-sm text-muted-foreground">
                      Manage system capacity limits and processing rules for your camera feeds.
                    </p>
                  </div>

                  <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                    <div className="rounded-xl bg-secondary/20 border border-white/5 p-4">
                      <p className="text-xs text-muted-foreground mb-1">Total Configured Cameras</p>
                      <p className="text-2xl font-bold text-foreground">
                        {metrics?.cameras?.total ?? 0}
                      </p>
                    </div>
                    <div className="rounded-xl bg-secondary/20 border border-white/5 p-4">
                      <p className="text-xs text-muted-foreground mb-1">Active AI Streams</p>
                      <p className="text-2xl font-bold text-status-online">
                        {metrics?.cameras?.running ?? 0}
                      </p>
                    </div>
                    <div className="rounded-xl bg-secondary/20 border border-white/5 p-4">
                      <p className="text-xs text-muted-foreground mb-1">Avg. Target FPS Per Stream</p>
                      <p className="text-2xl font-bold text-primary">
                        {metrics?.cameras?.running && metrics.cameras.running > 0
                          ? ((settings.cameras?.globalFpsTarget || 15) / metrics.cameras.running).toFixed(1)
                          : (settings.cameras?.globalFpsTarget || 15).toFixed(1)}{' '}
                        FPS
                      </p>
                    </div>
                  </div>

                  <div className="space-y-4 max-w-xl">
                    {/* Global Target FPS */}
                    <div className="rounded-xl border border-white/5 bg-secondary/10 p-5 space-y-4">
                      <div className="flex items-center justify-between">
                        <Label htmlFor="globalFpsTarget" className="text-base font-semibold">
                          Global Target FPS (Total System Capacity)
                        </Label>
                        <span className="text-sm font-mono bg-secondary px-2 py-0.5 rounded text-primary font-bold">
                          {settings.cameras?.globalFpsTarget || 15} FPS
                        </span>
                      </div>
                      
                      <div className="py-2">
                        <Slider
                          value={[settings.cameras?.globalFpsTarget || 15]}
                          min={1}
                          max={120}
                          step={1}
                          onValueChange={(value) =>
                            updateCameras({ globalFpsTarget: value[0] })
                          }
                        />
                      </div>

                      <div className="flex gap-4 items-center">
                        <span className="text-xs text-muted-foreground">1 FPS</span>
                        <div className="flex-1" />
                        <span className="text-xs text-muted-foreground">120 FPS</span>
                      </div>

                      <div className="space-y-2">
                        <Label htmlFor="globalFpsTargetInput" className="text-xs text-muted-foreground">
                          Or enter precise FPS target
                        </Label>
                        <Input
                          id="globalFpsTargetInput"
                          type="number"
                          min={1}
                          max={120}
                          value={settings.cameras?.globalFpsTarget || 15}
                          onChange={(e) =>
                            updateCameras({
                              globalFpsTarget: Math.max(1, Math.min(120, Number(e.target.value) || 1)),
                            })
                          }
                          className="w-24 bg-background/50 font-mono text-sm"
                        />
                      </div>

                      <p className="text-xs text-muted-foreground">
                        This limits the total combined frames the AI will process per second across all cameras, preventing CPU/GPU resource exhaustion and stabilizing system performance.
                      </p>
                    </div>

                    {/* End-to-end Latency Target */}
                    <div className="rounded-xl border border-white/5 bg-secondary/10 p-5 space-y-4">
                      <div className="flex items-center justify-between">
                        <Label htmlFor="targetLatencyMs" className="text-base font-semibold">
                          Target End-to-End Latency Threshold
                        </Label>
                        <span className="text-sm font-mono bg-secondary px-2 py-0.5 rounded text-primary font-bold">
                          {settings.cameras?.targetLatencyMs || 500} ms
                        </span>
                      </div>
                      
                      <div className="py-2">
                        <Slider
                          value={[settings.cameras?.targetLatencyMs || 500]}
                          min={100}
                          max={5000}
                          step={50}
                          onValueChange={(value) =>
                            updateCameras({ targetLatencyMs: value[0] })
                          }
                        />
                      </div>

                      <div className="flex gap-4 items-center">
                        <span className="text-xs text-muted-foreground">100 ms</span>
                        <div className="flex-1" />
                        <span className="text-xs text-muted-foreground">5000 ms</span>
                      </div>

                      <div className="space-y-2">
                        <Label htmlFor="targetLatencyMsInput" className="text-xs text-muted-foreground">
                          Or enter precise Latency target (ms)
                        </Label>
                        <Input
                          id="targetLatencyMsInput"
                          type="number"
                          min={100}
                          max={5000}
                          value={settings.cameras?.targetLatencyMs || 500}
                          onChange={(e) =>
                            updateCameras({
                              targetLatencyMs: Math.max(100, Math.min(5000, Number(e.target.value) || 100)),
                            })
                          }
                          className="w-24 bg-background/50 font-mono text-sm"
                        />
                      </div>

                      <p className="text-xs text-muted-foreground">
                        Defines the maximum acceptable delay between camera event occurrences and notification delivery before it's marked Critical.
                      </p>
                    </div>

                    {/* Target Memory GB */}
                    <div className="rounded-xl border border-white/5 bg-secondary/10 p-5 space-y-4">
                      <div className="flex items-center justify-between">
                        <div className="space-y-0.5">
                          <Label htmlFor="targetMemoryGb" className="text-base font-semibold">
                            Target Memory Limit Threshold
                          </Label>
                          {status?.memory_total_gb && (
                            <p className="text-xs text-muted-foreground">
                              Detected System Memory: {status.memory_total_gb.toFixed(1)} GB
                            </p>
                          )}
                        </div>
                        <span className="text-sm font-mono bg-secondary px-2 py-0.5 rounded text-primary font-bold">
                          {settings.cameras?.targetMemoryGb || 8.0} GB
                        </span>
                      </div>
                      
                      <div className="py-2">
                        <Slider
                          value={[settings.cameras?.targetMemoryGb || 8.0]}
                          min={1.0}
                          max={status?.memory_total_gb ? Math.ceil(status.memory_total_gb) : 16.0}
                          step={0.5}
                          onValueChange={(value) =>
                            updateCameras({ targetMemoryGb: value[0] })
                          }
                        />
                      </div>

                      <div className="flex gap-4 items-center">
                        <span className="text-xs text-muted-foreground">1 GB</span>
                        <div className="flex-1" />
                        <span className="text-xs text-muted-foreground">
                          {status?.memory_total_gb ? Math.ceil(status.memory_total_gb) : 16} GB
                        </span>
                      </div>

                      <div className="space-y-2">
                        <Label htmlFor="targetMemoryGbInput" className="text-xs text-muted-foreground">
                          Or enter precise Memory limit (GB)
                        </Label>
                        <Input
                          id="targetMemoryGbInput"
                          type="number"
                          min={1}
                          max={status?.memory_total_gb ? Math.ceil(status.memory_total_gb) : 16.0}
                          step={0.1}
                          value={settings.cameras?.targetMemoryGb || 8.0}
                          onChange={(e) =>
                            updateCameras({
                              targetMemoryGb: Math.max(1, Math.min(status?.memory_total_gb ? Math.ceil(status.memory_total_gb) : 16.0, Number(e.target.value) || 1)),
                            })
                          }
                          className="w-24 bg-background/50 font-mono text-sm"
                        />
                      </div>

                      <p className="text-xs text-muted-foreground">
                        Sets the RAM usage ceiling for model execution. Exceeding this triggers warnings or critical alerts.
                      </p>
                    </div>

                    {/* False Positive Rate Target */}
                    <div className="rounded-xl border border-white/5 bg-secondary/10 p-5 space-y-4">
                      <div className="flex items-center justify-between">
                        <Label htmlFor="targetFalsePositiveRate" className="text-base font-semibold">
                          Target False Positive Rate Threshold
                        </Label>
                        <span className="text-sm font-mono bg-secondary px-2 py-0.5 rounded text-primary font-bold">
                          {settings.cameras?.targetFalsePositiveRate || 5.0}%
                        </span>
                      </div>
                      
                      <div className="py-2">
                        <Slider
                          value={[settings.cameras?.targetFalsePositiveRate || 5.0]}
                          min={0.5}
                          max={30.0}
                          step={0.5}
                          onValueChange={(value) =>
                            updateCameras({ targetFalsePositiveRate: value[0] })
                          }
                        />
                      </div>

                      <div className="flex gap-4 items-center">
                        <span className="text-xs text-muted-foreground">0.5%</span>
                        <div className="flex-1" />
                        <span className="text-xs text-muted-foreground">30.0%</span>
                      </div>

                      <div className="space-y-2">
                        <Label htmlFor="targetFalsePositiveRateInput" className="text-xs text-muted-foreground">
                          Or enter precise False Positive Rate (%)
                        </Label>
                        <Input
                          id="targetFalsePositiveRateInput"
                          type="number"
                          min={0.5}
                          max={30}
                          step={0.1}
                          value={settings.cameras?.targetFalsePositiveRate || 5.0}
                          onChange={(e) =>
                            updateCameras({
                              targetFalsePositiveRate: Math.max(0.5, Math.min(30, Number(e.target.value) || 0.5)),
                            })
                          }
                          className="w-24 bg-background/50 font-mono text-sm"
                        />
                      </div>

                      <p className="text-xs text-muted-foreground">
                        Defines the target maximum proportion of system events classified as false positives.
                      </p>
                    </div>
                  </div>
                </div>
              )}
              </div>{/* end px-6 pb-6 */}
            </div>{/* end content scroll area */}
          </div>
        </div>
      </div>
    </div>
  );
}
