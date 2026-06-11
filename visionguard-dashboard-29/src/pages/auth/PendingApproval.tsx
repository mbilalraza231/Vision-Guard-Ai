import { useNavigate } from 'react-router-dom';
import { useAuth } from '@/contexts/AuthContext';
import { Button } from '@/components/ui/button';
import { ShieldAlert, LogOut } from 'lucide-react';
import { useTranslation } from 'react-i18next';

export default function PendingApproval() {
  const { logout } = useAuth();
  const navigate = useNavigate();
  const { t } = useTranslation();

  const handleLogout = async () => {
    await logout();
    navigate('/auth/login');
  };

  return (
    <div className="animate-fade-in w-full max-w-md p-8 bg-card border border-border rounded-2xl shadow-xl text-center mx-auto">
      <div className="flex justify-center mb-6">
        <div className="h-16 w-16 bg-amber-500/10 text-amber-500 rounded-full flex items-center justify-center border border-amber-500/20">
          <ShieldAlert className="h-8 w-8" />
        </div>
      </div>
      
      <h1 className="text-2xl font-bold text-foreground mb-2">Approval Pending</h1>
      <p className="text-muted-foreground mb-8">
        Your account has been created successfully, but it requires administrator approval before you can access the dashboard.
        Please contact your system administrator to activate your account.
      </p>

      <Button onClick={handleLogout} variant="outline" className="w-full gap-2 border-border/50">
        <LogOut className="h-4 w-4" />
        Sign Out
      </Button>
    </div>
  );
}
