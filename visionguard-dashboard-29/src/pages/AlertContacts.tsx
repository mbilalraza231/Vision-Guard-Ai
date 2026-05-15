import { useState, useEffect } from 'react';
import { Header } from '@/components/layout/Header';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Switch } from '@/components/ui/switch';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from '@/components/ui/dialog';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import {
  Bell, Mail, Phone, Plus, Trash2, Search, UserCheck, Shield, History,
  ExternalLink, CheckCircle2, Clock, XCircle, AlertCircle, Filter, Edit2
} from 'lucide-react';
import { useQuery } from '@tanstack/react-query';
import { apiService } from '@/services/api.service';
import { API_ENDPOINTS } from '@/config/api';
import { cn } from '@/lib/utils';

const STORAGE_KEY = 'vg:dashboard:settings';

export default function AlertContacts() {
  const [activeTab, setActiveTab] = useState<'contacts' | 'history'>('contacts');
  const [isAddModalOpen, setIsAddModalOpen] = useState(false);
  const [selectedRecipientId, setSelectedRecipientId] = useState<string | null>(null);
  const [newRecipient, setNewRecipient] = useState({
    name: '',
    phone: '',
    email: '',
    whatsapp: true,
    emailAlert: true,
    minSeverity: 'medium' as 'critical' | 'high' | 'medium' | 'low'
  });
  const [searchQuery, setSearchQuery] = useState('');

  // Fetch contacts from backend
  const { data: contactsResponse, refetch: refetchContacts, isLoading: contactsLoading } = useQuery({
    queryKey: ['alert-contacts'],
    queryFn: () => apiService.getData<any>(API_ENDPOINTS.alerts.contacts.list),
  });

  const recipients = contactsResponse?.contacts ?? [];

  const addRecipient = async () => {
    if (!newRecipient.name) {
      alert("Please enter a name.");
      return;
    }
    if (!newRecipient.phone && !newRecipient.email) {
      alert("Please enter at least a phone number or an email.");
      return;
    }

    try {
      if (selectedRecipientId) {
        await updateRecipient(selectedRecipientId, {
          name: newRecipient.name,
          phone: newRecipient.phone,
          email: newRecipient.email,
          whatsapp: newRecipient.whatsapp,
          emailAlert: newRecipient.emailAlert,
          minSeverity: newRecipient.minSeverity
        });
      } else {
        await apiService.postData(API_ENDPOINTS.alerts.contacts.create, {
          name: newRecipient.name,
          phone: newRecipient.phone,
          email: newRecipient.email,
          whatsapp: newRecipient.whatsapp,
          email_alert: newRecipient.emailAlert,
          min_severity: newRecipient.minSeverity,
          is_active: true
        });
      }
      refetchContacts();
      setNewRecipient({ name: '', phone: '', email: '', whatsapp: true, emailAlert: true, minSeverity: 'medium' });
      setSelectedRecipientId(null);
      setIsAddModalOpen(false);
    } catch (e: any) {
      console.error('Failed to save contact', e);
      alert(`Error: ${e.message || "Failed to save contact. Please try again."}`);
    }
  };

  const deleteRecipient = async (id: string) => {
    try {
      await apiService.deleteData(API_ENDPOINTS.alerts.contacts.delete(id));
      refetchContacts();
    } catch (e) {
      console.error('Failed to delete contact', e);
    }
  };

  const updateRecipient = async (id: string, patch: any) => {
    try {
      // Map frontend field names to backend snake_case if necessary
      const backendPatch = { ...patch };
      if (patch.minSeverity) {
        backendPatch.min_severity = patch.minSeverity;
        delete backendPatch.minSeverity;
      }
      if (patch.emailAlert !== undefined) {
        backendPatch.email_alert = patch.emailAlert;
        delete backendPatch.emailAlert;
      }

      await apiService.putData(API_ENDPOINTS.alerts.contacts.update(id), backendPatch);
      refetchContacts();
    } catch (e) {
      console.error('Failed to update contact', e);
    }
  };

  const toggleAlert = (id: string, type: 'whatsapp' | 'emailAlert') => {
    const contact = recipients.find(r => r.id === id);
    if (!contact) return;
    
    updateRecipient(id, { [type]: !contact[type === 'emailAlert' ? 'email_alert' : type] });
  };

  const filteredRecipients = recipients.filter((r: any) =>
    r.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
    (r.phone && r.phone.includes(searchQuery))
  );

  // Load Alert History from Backend — now powered by Global SSE Stream
  const { data: alertHistory, isLoading: historyLoading } = useQuery({
    queryKey: ['alert-history'],
    queryFn: () => apiService.getData<any>(API_ENDPOINTS.alerts.list),
    enabled: activeTab === 'history',
  });

  const alerts = alertHistory?.alerts ?? [];

  return (
    <div className="min-h-screen">
      <Header title="Alerts" showDateNav={false} />

      <div className="p-6 max-w-6xl mx-auto">
        {/* Tab Navigation */}
        <div className="flex gap-1 p-1 bg-secondary/20 rounded-xl w-fit mb-8">
          <button
            onClick={() => setActiveTab('contacts')}
            className={cn(
              "px-6 py-2 text-sm font-bold rounded-lg transition-all",
              activeTab === 'contacts' ? "bg-primary text-primary-foreground shadow-lg" : "text-muted-foreground hover:text-white"
            )}
          >
            Contacts
          </button>
          <button
            onClick={() => setActiveTab('history')}
            className={cn(
              "px-6 py-2 text-sm font-bold rounded-lg transition-all",
              activeTab === 'history' ? "bg-primary text-primary-foreground shadow-lg" : "text-muted-foreground hover:text-white"
            )}
          >
            History
          </button>
        </div>

        {activeTab === 'contacts' ? (
          <div className="animate-fade-in">
            {/* Top Actions */}
            <div className="flex flex-col md:flex-row items-center justify-between gap-4 mb-8">
              <div className="relative w-full md:w-96">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                <Input
                  placeholder="Search contacts..."
                  className="pl-10 bg-secondary/20 border-white/5"
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                />
              </div>

              <Button className="w-full md:w-auto gap-2" onClick={() => { setSelectedRecipientId(null); setIsAddModalOpen(true); }}>
                <Plus className="h-4 w-4" /> Add New Contact
              </Button>
            </div>

            {/* Info Box */}
            <div className="mb-8 rounded-xl border border-primary/20 bg-primary/5 p-4 flex items-start gap-4">
              <div className="p-2 rounded-lg bg-primary/10">
                <Shield className="h-5 w-5 text-primary" />
              </div>
              <div>
                <h3 className="font-semibold text-primary">Notification Policy</h3>
                <p className="text-sm text-muted-foreground mt-1">
                  These contacts will receive real-time alerts when incidents occur.
                  Ensure phone numbers include country codes (e.g., +1 for USA, +92 for Pakistan).
                </p>
              </div>
            </div>

            {/* Contacts Grid */}
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
              {filteredRecipients.map((r) => (
                <div key={r.id} className="group relative rounded-2xl border border-white/5 bg-secondary/10 p-5 transition-all hover:bg-secondary/20 hover:border-primary/20 shadow-lg">
                  <div className="flex items-start justify-between mb-4">
                    <div className="flex items-center gap-3">
                      <div className="flex h-12 w-12 items-center justify-center rounded-full bg-primary/10 text-primary text-lg font-bold">
                        {r.name.charAt(0)}
                      </div>
                      <div>
                        <h3 className="font-bold text-lg">{r.name}</h3>
                        <div className="flex items-center gap-1 text-xs text-status-online">
                          <UserCheck className="h-3 w-3" /> Active Recipient
                        </div>
                      </div>
                    </div>
                    <div className="flex gap-1 opacity-0 group-hover:opacity-100 transition-all">
                      <Button
                        variant="ghost"
                        size="icon"
                        className="h-8 w-8 text-muted-foreground hover:text-primary"
                        onClick={() => {
                          setNewRecipient({
                            name: r.name,
                            phone: r.phone || '',
                            email: r.email || '',
                            whatsapp: r.whatsapp,
                            emailAlert: r.email_alert,
                            minSeverity: r.min_severity as any
                          });
                          setSelectedRecipientId(r.id);
                          setIsAddModalOpen(true);
                        }}
                      >
                        <Edit2 className="h-4 w-4" />
                      </Button>
                      <Button
                        variant="ghost"
                        size="icon"
                        className="h-8 w-8 text-muted-foreground hover:text-severity-critical"
                        onClick={() => deleteRecipient(r.id)}
                      >
                        <Trash2 className="h-4 w-4" />
                      </Button>
                    </div>
                  </div>

                  <div className="space-y-3 mb-6">
                    <div className="flex items-center gap-3 text-sm text-muted-foreground">
                      <Phone className="h-4 w-4" /> {r.phone}
                    </div>
                    <div className="flex items-center gap-3 text-sm text-muted-foreground">
                      <Mail className="h-4 w-4" /> {r.email || 'No email provided'}
                    </div>
                  </div>

                  <div className="flex items-center justify-between pt-4 border-t border-white/5 mb-4">
                    <div className="flex flex-col gap-1.5">
                      <span className="text-[10px] uppercase tracking-wider text-muted-foreground font-bold flex items-center gap-1">
                        <Filter className="h-2 w-2" /> Min Severity
                      </span>
                      <Select
                        value={r.min_severity || 'medium'}
                        onValueChange={(val) => updateRecipient(r.id, { min_severity: val })}
                      >
                        <SelectTrigger className="h-7 w-28 text-[10px] bg-white/5 border-none">
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent className="bg-[#1a1c23] border-white/10 text-white">
                          <SelectItem value="low">Low+</SelectItem>
                          <SelectItem value="medium">Medium+</SelectItem>
                          <SelectItem value="high">High+</SelectItem>
                          <SelectItem value="critical">Critical Only</SelectItem>
                        </SelectContent>
                      </Select>
                    </div>
                    <div className="flex gap-4">
                      <div className="flex flex-col gap-1">
                        <span className="text-[10px] uppercase tracking-wider text-muted-foreground font-bold">WhatsApp</span>
                        <Switch
                          checked={r.whatsapp}
                          onCheckedChange={() => toggleAlert(r.id, 'whatsapp')}
                        />
                      </div>
                      <div className="flex flex-col gap-1">
                        <span className="text-[10px] uppercase tracking-wider text-muted-foreground font-bold">Email</span>
                        <Switch
                          checked={r.email_alert}
                          onCheckedChange={() => toggleAlert(r.id, 'emailAlert')}
                        />
                      </div>
                    </div>
                  </div>
                </div>
              ))}

              {filteredRecipients.length === 0 && (
                <div className="col-span-full py-20 text-center rounded-2xl border border-dashed border-white/10 bg-secondary/5">
                  <Bell className="h-12 w-12 text-muted-foreground/20 mx-auto mb-4" />
                  <h3 className="text-xl font-semibold text-muted-foreground">No contacts found</h3>
                  <p className="text-muted-foreground/60">Start by adding your first alert recipient.</p>
                </div>
              )}
            </div>
          </div>
        ) : (
          <div className="animate-fade-in">
            <div className="flex justify-end mb-3 px-2">
              <div className="flex items-center gap-4 text-[10px] uppercase font-bold tracking-widest text-muted-foreground/60">
                <div className="flex items-center gap-1.5">
                  <div className="h-2 w-2 rounded-full bg-status-online shadow-[0_0_8px_rgba(46,213,115,0.4)]"></div>
                  <span>Sent</span>
                </div>
                <div className="flex items-center gap-1.5">
                  <div className="h-2 w-2 rounded-full bg-severity-critical shadow-[0_0_8px_rgba(255,75,43,0.4)]"></div>
                  <span>Failed</span>
                </div>
              </div>
            </div>
            <div className="rounded-2xl border border-white/5 bg-secondary/10 overflow-hidden shadow-2xl">
              <table className="w-full text-left border-collapse">
                <thead className="bg-white/5 border-b border-white/5">
                  <tr>
                    <th className="p-4 text-xs font-bold uppercase tracking-wider text-muted-foreground">Time</th>
                    <th className="p-4 text-xs font-bold uppercase tracking-wider text-muted-foreground">Recipient</th>
                    <th className="p-4 text-xs font-bold uppercase tracking-wider text-muted-foreground">Channel</th>
                    <th className="p-4 text-xs font-bold uppercase tracking-wider text-muted-foreground">Status</th>
                    <th className="p-4 text-xs font-bold uppercase tracking-wider text-right text-muted-foreground">Action</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-white/5">
                  {alerts.map((alert: any) => (
                    <tr key={alert.id} className="hover:bg-white/5 transition-colors group">
                      <td className="p-4 text-sm font-mono text-muted-foreground">
                        {new Date(alert.created_at * 1000).toLocaleString()}
                      </td>
                      <td className="p-4">
                        <div className="font-semibold">{alert.recipient || 'Unknown'}</div>
                        <div className="text-[10px] text-muted-foreground font-mono">#{alert.id.slice(0, 8)}</div>
                      </td>
                      <td className="p-4">
                        {alert.channel === 'multi-channel' ? (
                          <div className="flex items-center gap-3">
                            <div className={cn(
                              "flex items-center gap-1",
                              alert.details?.whatsapp === false ? "text-severity-critical" : "text-status-online"
                            )}>
                              <Phone className="h-3.5 w-3.5" /> <span className="text-[10px]">WA</span>
                            </div>
                            <div className={cn(
                              "flex items-center gap-1",
                              alert.details?.email === false ? "text-severity-critical" : "text-status-online"
                            )}>
                              <Mail className="h-3.5 w-3.5" /> <span className="text-[10px]">Email</span>
                            </div>
                          </div>
                        ) : alert.channel === 'whatsapp' || alert.channel === 'sms' ? (
                          <div className={cn(
                            "flex items-center gap-2",
                            alert.status === 'failed' ? "text-severity-critical" : "text-status-online"
                          )}>
                            <Phone className="h-4 w-4" /> <span className="text-xs">WhatsApp</span>
                          </div>
                        ) : (
                          <div className={cn(
                            "flex items-center gap-2",
                            alert.status === 'failed' ? "text-severity-critical" : "text-status-online"
                          )}>
                            <Mail className="h-4 w-4" /> <span className="text-xs">Email</span>
                          </div>
                        )}
                      </td>
                      <td className="p-4">
                        <div className={cn(
                          "inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-bold uppercase",
                          alert.status === 'sent' && "bg-status-online/10 text-status-online",
                          alert.status === 'pending' && "bg-amber-500/10 text-amber-500",
                          alert.status === 'failed' && "bg-severity-critical/10 text-severity-critical"
                        )}>
                          {alert.status === 'sent' && <CheckCircle2 className="h-3 w-3" />}
                          {alert.status === 'pending' && <Clock className="h-3 w-3 animate-pulse" />}
                          {alert.status === 'failed' && <XCircle className="h-3 w-3" />}
                          {alert.status}
                        </div>
                        {alert.error_message && (
                          <div className="text-[10px] text-severity-critical mt-1 flex items-center gap-1">
                            <AlertCircle className="h-2 w-2" /> {alert.error_message}
                          </div>
                        )}
                      </td>
                      <td className="p-4 text-right">
                        <Button 
                          variant="ghost" 
                          size="icon" 
                          className="h-8 w-8 opacity-0 group-hover:opacity-100 transition-opacity"
                          onClick={() => window.location.href = `/incidents/${alert.event_id}`}
                        >
                          <ExternalLink className="h-4 w-4 text-muted-foreground" />
                        </Button>
                      </td>
                    </tr>
                  ))}
                  {alerts.length === 0 && !historyLoading && (
                    <tr>
                      <td colSpan={5} className="p-20 text-center text-muted-foreground">
                        <History className="h-12 w-12 mx-auto mb-4 opacity-10" />
                        No alert history recorded yet.
                      </td>
                    </tr>
                  )}
                  {historyLoading && (
                    <tr>
                      <td colSpan={5} className="p-20 text-center text-muted-foreground animate-pulse">
                        Loading alert history...
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </div>

      {/* Add Modal */}
      {isAddModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
          <div className="relative w-full max-w-md bg-card border border-border rounded-2xl p-6">
            <div className="flex items-center justify-between mb-6">
              <h2 className="text-lg font-bold">
                {selectedRecipientId ? 'Edit Alert Recipient' : 'Add New Alert Recipient'}
              </h2>
              <button onClick={() => setIsAddModalOpen(false)} className="h-8 w-8 hover:bg-secondary rounded-lg flex items-center justify-center">
                <XCircle className="h-4 w-4" />
              </button>
            </div>
            
            <div className="space-y-4">
              <div>
                <label className="text-xs font-medium text-muted-foreground mb-1 block">Full Name *</label>
                <input
                  type="text"
                  value={newRecipient.name}
                  onChange={e => setNewRecipient(f => ({ ...f, name: e.target.value }))}
                  className="w-full bg-secondary border border-border rounded-lg px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-primary/40"
                  required
                />
              </div>
              
              <div>
                <label className="text-xs font-medium text-muted-foreground mb-1 block">WhatsApp Phone *</label>
                <input
                  type="text"
                  value={newRecipient.phone}
                  onChange={e => setNewRecipient(f => ({ ...f, phone: e.target.value }))}
                  className="w-full bg-secondary border border-border rounded-lg px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-primary/40"
                  required
                />
              </div>

              <div>
                <label className="text-xs font-medium text-muted-foreground mb-1 block">Email Address</label>
                <input
                  type="email"
                  value={newRecipient.email}
                  onChange={e => setNewRecipient(f => ({ ...f, email: e.target.value }))}
                  className="w-full bg-secondary border border-border rounded-lg px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-primary/40"
                />
              </div>

              <div>
                <label className="text-xs font-medium text-muted-foreground mb-1 block">Minimum Severity</label>
                <select
                  value={newRecipient.minSeverity}
                  onChange={e => setNewRecipient(f => ({ ...f, minSeverity: e.target.value as any }))}
                  className="w-full bg-secondary border border-border rounded-lg px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-primary/40"
                >
                  <option value="low">Low (All alerts)</option>
                  <option value="medium">Medium+</option>
                  <option value="high">High+</option>
                  <option value="critical">Critical Only</option>
                </select>
              </div>

              <div className="flex items-center justify-around rounded-lg bg-secondary/50 p-3 border border-border mt-2">
                <div className="flex flex-col items-center gap-1">
                  <label className="text-[10px] uppercase font-bold text-muted-foreground">WhatsApp</label>
                  <Switch 
                    checked={newRecipient.whatsapp}
                    onCheckedChange={(v) => setNewRecipient(f => ({ ...f, whatsapp: v }))}
                  />
                </div>
                <div className="flex flex-col items-center gap-1">
                  <label className="text-[10px] uppercase font-bold text-muted-foreground">Email</label>
                  <Switch 
                    checked={newRecipient.emailAlert}
                    onCheckedChange={(v) => setNewRecipient(f => ({ ...f, emailAlert: v }))}
                  />
                </div>
              </div>
            </div>

            <div className="flex gap-3 pt-5">
              <Button type="button" variant="outline" className="flex-1" onClick={() => setIsAddModalOpen(false)}>Cancel</Button>
              <Button onClick={addRecipient} className="flex-1 gap-2">
                <Plus className="h-4 w-4" /> Save Contact
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
