import { useState, useEffect } from 'react';
import { Header } from '@/components/layout/Header';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Avatar, AvatarFallback, AvatarImage } from '@/components/ui/avatar';
import { useAuth } from '@/contexts/AuthContext';
import { useProfile, useUpdateProfile } from '@/hooks/useProfile';
import { Loader2, User, Mail, Shield, Camera, Save, Key } from 'lucide-react';
import { toast } from 'sonner';
import { useTranslation } from 'react-i18next';

export default function Profile() {
  const { t } = useTranslation();
  const { data: user, isLoading: isProfileLoading } = useProfile();
  const updateProfile = useUpdateProfile();
  
  const [formData, setFormData] = useState({
    name: user?.name || '',
    email: user?.email || '',
  });

  // 1. GLOBAL SYNC: Keep form updated if user data changes elsewhere (e.g. User Management page)
  useEffect(() => {
    if (user) {
      console.log('[Profile] Syncing form with global user state:', user.name);
      setFormData(prev => ({
        ...prev,
        name: user.name || '',
        email: user.email || ''
      }));
    }
  }, [user]);

  const handleUpdateProfile = async (e: React.FormEvent) => {
    e.preventDefault();
    if (updateProfile.isPending) return;
    
    try {
      await updateProfile.mutateAsync({ name: formData.name });
      toast.success('Profile updated successfully');
    } catch (err) {
      console.error('[Profile] Update error:', err);
      const error = err as Error;
      toast.error(error.message || 'Failed to update profile');
    }
  };

  if (!user) return null;

  return (
    <div className="min-h-screen">
      <Header title={t('profile.title')} showDateNav={false} />
      
      <div className="p-6 max-w-4xl mx-auto">
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          {/* Avatar Section */}
          <div className="md:col-span-1 space-y-6">
            <div className="dashboard-card p-6 flex flex-col items-center text-center">
              <div className="relative mb-4">
                <Avatar className="h-32 w-32 border-4 border-primary/20">
                  <AvatarImage src={user.avatar} />
                  <AvatarFallback className="bg-primary/10 text-primary text-4xl">
                    {user.name.split(' ').map(n => n[0]).join('')}
                  </AvatarFallback>
                </Avatar>
                <Button 
                  size="icon" 
                  className="absolute bottom-0 right-0 rounded-full h-10 w-10 border-4 border-background"
                >
                  <Camera className="h-4 w-4" />
                </Button>
              </div>
              <h3 className="text-xl font-bold">{user.name}</h3>
              <p className="text-sm text-muted-foreground capitalize mb-4">{user.role}</p>
              <div className="w-full pt-4 border-t border-white/5 space-y-2">
                <div className="flex items-center gap-2 text-sm text-muted-foreground">
                  <Mail className="h-4 w-4" />
                  {user.email}
                </div>
                <div className="flex items-center gap-2 text-sm text-muted-foreground">
                  <Shield className="h-4 w-4" />
                  Role: <span className="capitalize text-foreground font-medium">{user.role}</span>
                </div>
              </div>
            </div>
          </div>

          {/* Settings Section */}
          <div className="md:col-span-2 space-y-6">
            <div className="dashboard-card p-6">
              <div className="flex items-center gap-2 mb-6">
                <User className="h-5 w-5 text-primary" />
                <h3 className="text-xl font-bold">{t('profile.personalInfo')}</h3>
              </div>
              
              <form onSubmit={handleUpdateProfile} className="space-y-4">
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                  <div className="space-y-2">
                    <Label htmlFor="name">{t('profile.fullName')}</Label>
                    <Input 
                      id="name" 
                      value={formData.name} 
                      onChange={e => setFormData({...formData, name: e.target.value})}
                      className="bg-secondary/50" 
                    />
                  </div>
                  <div className="space-y-2">
                    <Label htmlFor="email">{t('profile.email')}</Label>
                    <Input 
                      id="email" 
                      type="email" 
                      value={formData.email} 
                      disabled
                      className="bg-secondary/50 opacity-50 cursor-not-allowed" 
                    />
                    <p className="text-[10px] text-muted-foreground">{t('profile.emailHint')}</p>
                  </div>
                </div>

                <div className="flex justify-end pt-4">
                  <Button type="submit" className="gap-2" disabled={updateProfile.isPending}>
                    {updateProfile.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />}
                    {t('profile.saveChanges')}
                  </Button>
                </div>
              </form>
            </div>

            <div className="dashboard-card p-6">
              <div className="flex items-center gap-2 mb-6">
                <Key className="h-5 w-5 text-primary" />
                <h3 className="text-xl font-bold">{t('profile.security')}</h3>
              </div>
              
              <div className="space-y-4">
                <p className="text-sm text-muted-foreground">
                  {t('profile.passwordReset')}
                </p>
                <Button variant="outline" className="gap-2">
                  {t('profile.sendReset')}
                </Button>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
