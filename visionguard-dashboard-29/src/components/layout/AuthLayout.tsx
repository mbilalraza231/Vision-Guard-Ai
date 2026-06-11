import { useEffect } from 'react';
import { Outlet, useNavigate, useLocation } from 'react-router-dom';
import { Target, ShieldCheck, Zap, BarChart3 } from 'lucide-react';
import { useAuth } from '@/contexts/AuthContext';

export function AuthLayout() {
  const { isAuthenticated, isLoading } = useAuth();
  const navigate = useNavigate();

  const location = useLocation();

  useEffect(() => {
    // Do not redirect authenticated users if they are on the pending-approval
    // or update-password pages (recovery links auto-authenticate the user!)
    const isExcludedPage = 
      location.pathname === '/auth/pending-approval' || 
      location.pathname === '/auth/update-password';

    if (!isLoading && isAuthenticated && !isExcludedPage) {
      navigate('/dashboard');
    }
  }, [isAuthenticated, isLoading, navigate, location.pathname]);

  if (isLoading) return null;

  return (
    <div className="flex h-screen max-h-screen w-screen bg-background overflow-hidden relative">
      {/* Background Orbs and Grid */}
      <div className="absolute inset-0 overflow-hidden pointer-events-none -z-10">
        <div className="absolute inset-0 bg-[linear-gradient(to_right,#8080800a_1px,transparent_1px),linear-gradient(to_bottom,#8080800a_1px,transparent_1px)] bg-[size:14px_24px] [mask-image:radial-gradient(ellipse_60%_50%_at_50%_0%,#000_70%,transparent_100%)]" />
        <div className="absolute -top-[20%] -left-[10%] w-[50%] h-[50%] rounded-full bg-primary/20 blur-[120px] mix-blend-screen animate-pulse" />
        <div className="absolute top-[60%] left-[30%] w-[40%] h-[40%] rounded-full bg-blue-500/10 blur-[100px] mix-blend-screen" />
        <div className="absolute bottom-[10%] right-[10%] w-[30%] h-[30%] rounded-full bg-indigo-500/10 blur-[120px] mix-blend-screen" />
      </div>

      {/* Left side - Branding */}
      <div className="hidden w-1/2 flex-col justify-center p-8 xl:p-12 lg:flex relative h-full overflow-hidden select-none">
        <div className="flex flex-col max-w-xl mx-auto w-full z-10 justify-between h-[80vh] max-h-[640px]">
          
          {/* Brand Info & Heading */}
          <div>
            <div className="flex items-center gap-3 mb-4">
              <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-black/40 border border-white/10 backdrop-blur-md shadow-xl overflow-hidden">
                <img src="/favicon.png" alt="VisionGuard Logo" className="w-full h-full object-cover scale-110" />
              </div>
              <div>
                <h1 className="text-xl font-bold tracking-tight bg-gradient-to-br from-foreground to-foreground/60 bg-clip-text text-transparent">VisionGuard AI</h1>
              </div>
            </div>
            
            <h2 className="text-3xl xl:text-4xl font-extrabold leading-[1.15] mb-3 tracking-tight text-foreground">
              Enterprise-grade security<br />
              <span className="bg-gradient-to-r from-primary via-blue-500 to-indigo-500 bg-clip-text text-transparent">AI-powered surveillance.</span><br />
              Built for operators.
            </h2>
            
            <p className="text-sm text-muted-foreground max-w-md leading-relaxed">
              Sign in to access your command center — cameras, alerts, and AI analytics are waiting for you.
            </p>
          </div>

          {/* Grid Feature List */}
          <div className="grid grid-cols-2 gap-4 mt-8">
            
            {/* Feature 1 */}
            <div className="group relative rounded-2xl border border-white/[0.03] bg-white/[0.01] p-4 backdrop-blur-sm transition-all duration-300 hover:border-primary/20 hover:bg-primary/[0.02]">
              <div className="flex items-center gap-3 mb-2">
                <div className="h-9 w-9 rounded-xl bg-primary/10 flex items-center justify-center shrink-0 border border-primary/20 transition-transform duration-300 group-hover:scale-105">
                  <Target className="h-4.5 w-4.5 text-primary" />
                </div>
                <h3 className="text-sm font-bold text-foreground tracking-tight">Real-time AI detection</h3>
              </div>
              <p className="text-xs text-muted-foreground leading-normal">
                Motion, intrusion, face & object recognition across all zones
              </p>
            </div>

            {/* Feature 2 */}
            <div className="group relative rounded-2xl border border-white/[0.03] bg-white/[0.01] p-4 backdrop-blur-sm transition-all duration-300 hover:border-blue-500/20 hover:bg-blue-500/[0.02]">
              <div className="flex items-center gap-3 mb-2">
                <div className="h-9 w-9 rounded-xl bg-blue-500/10 flex items-center justify-center shrink-0 border border-blue-500/20 transition-transform duration-300 group-hover:scale-105">
                  <Zap className="h-4.5 w-4.5 text-blue-500" />
                </div>
                <h3 className="text-sm font-bold text-foreground tracking-tight">Instant alert routing</h3>
              </div>
              <p className="text-xs text-muted-foreground leading-normal">
                Smart alerts sent to the right team, automatically
              </p>
            </div>

            {/* Feature 3 */}
            <div className="group relative rounded-2xl border border-white/[0.03] bg-white/[0.01] p-4 backdrop-blur-sm transition-all duration-300 hover:border-emerald-500/20 hover:bg-emerald-500/[0.02]">
              <div className="flex items-center gap-3 mb-2">
                <div className="h-9 w-9 rounded-xl bg-emerald-500/10 flex items-center justify-center shrink-0 border border-emerald-500/20 transition-transform duration-300 group-hover:scale-105">
                  <ShieldCheck className="h-4.5 w-4.5 text-emerald-500" />
                </div>
                <h3 className="text-sm font-bold text-foreground tracking-tight">Zero-trust access control</h3>
              </div>
              <p className="text-xs text-muted-foreground leading-normal">
                Role-based permissions with full audit logs
              </p>
            </div>

            {/* Feature 4 */}
            <div className="group relative rounded-2xl border border-white/[0.03] bg-white/[0.01] p-4 backdrop-blur-sm transition-all duration-300 hover:border-indigo-500/20 hover:bg-indigo-500/[0.02]">
              <div className="flex items-center gap-3 mb-2">
                <div className="h-9 w-9 rounded-xl bg-indigo-500/10 flex items-center justify-center shrink-0 border border-indigo-500/20 transition-transform duration-300 group-hover:scale-105">
                  <BarChart3 className="h-4.5 w-4.5 text-indigo-400" />
                </div>
                <h3 className="text-sm font-bold text-foreground tracking-tight">Analytics & reporting</h3>
              </div>
              <p className="text-xs text-muted-foreground leading-normal">
                Heatmaps, incident trends, and daily summaries
              </p>
            </div>

          </div>
        </div>
      </div>

      {/* Right side - Auth Form */}
      <div className="flex w-full items-center justify-center p-6 sm:p-8 lg:w-1/2 relative z-10 bg-background/50 backdrop-blur-xl border-l border-white/5 shadow-2xl h-full overflow-y-auto">
        <div className="w-full max-w-md">
          {/* Mobile logo */}
          <div className="mb-8 flex items-center gap-3 lg:hidden">
            <div className="flex h-12 w-12 items-center justify-center rounded-xl bg-black/40 border border-white/10 backdrop-blur-md shadow-xl overflow-hidden">
              <img src="/favicon.png" alt="VisionGuard Logo" className="w-full h-full object-cover scale-110" />
            </div>
            <div>
              <h1 className="text-2xl font-bold text-foreground">VisionGuard AI</h1>
            </div>
          </div>

          <Outlet />
        </div>
      </div>
    </div>
  );
}
