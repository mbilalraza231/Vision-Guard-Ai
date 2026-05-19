import { useEffect } from 'react';
import { Outlet, useNavigate } from 'react-router-dom';
import { Activity, Target, ShieldCheck, Zap } from 'lucide-react';
import { useAuth } from '@/contexts/AuthContext';

export function AuthLayout() {
  const { isAuthenticated, isLoading } = useAuth();
  const navigate = useNavigate();

  useEffect(() => {
    if (!isLoading && isAuthenticated) {
      navigate('/dashboard');
    }
  }, [isAuthenticated, isLoading, navigate]);

  if (isLoading) return null;

  return (
    <div className="flex min-h-screen bg-background overflow-hidden relative">
      {/* Background Orbs */}
      <div className="absolute top-0 left-0 w-full h-full overflow-hidden pointer-events-none -z-10">
        <div className="absolute -top-[20%] -left-[10%] w-[50%] h-[50%] rounded-full bg-primary/20 blur-[120px] mix-blend-screen animate-pulse" />
        <div className="absolute top-[60%] left-[30%] w-[40%] h-[40%] rounded-full bg-blue-500/10 blur-[100px] mix-blend-screen" />
      </div>

      {/* Left side - Branding */}
      <div className="hidden w-1/2 flex-col justify-center p-12 lg:flex relative">
        <div className="flex flex-col max-w-xl mx-auto w-full z-10">
          
          <div className="flex items-center gap-4 mb-10">
            <div className="flex h-14 w-14 items-center justify-center rounded-2xl bg-black/40 border border-white/10 backdrop-blur-md shadow-xl overflow-hidden p-1">
              <img src="/logo.png" alt="VisionGuard Logo" className="w-full h-full object-contain" />
            </div>
            <div>
              <h1 className="text-3xl font-extrabold tracking-tight bg-gradient-to-br from-foreground to-foreground/60 bg-clip-text text-transparent">VisionGuard AI</h1>
              <div className="flex items-center gap-2 mt-1">
                <span className="flex h-2 w-2 rounded-full bg-emerald-500 animate-pulse" />
                <p className="text-sm font-medium text-emerald-500/90 tracking-wider uppercase">System Active</p>
              </div>
            </div>
          </div>
          
          <h2 className="text-5xl font-black leading-[1.1] mb-6 tracking-tight text-foreground">
            Next-Gen <br />
            <span className="bg-gradient-to-r from-primary via-blue-500 to-indigo-500 bg-clip-text text-transparent">Surveillance Intelligence</span>
          </h2>
          
          <p className="text-lg text-muted-foreground max-w-md mb-12 leading-relaxed">
            Military-grade anomaly detection and real-time behavioral analysis, powered by state-of-the-art vision models.
          </p>

          {/* Bento Box Stats */}
          <div className="grid grid-cols-2 gap-4">
            
            {/* Stat 1 */}
            <div className="group relative rounded-2xl bg-black/20 hover:bg-black/40 border border-white/5 hover:border-primary/30 p-5 backdrop-blur-md transition-all duration-300 hover:-translate-y-1 shadow-2xl">
              <div className="absolute inset-0 bg-gradient-to-br from-primary/10 to-transparent opacity-0 group-hover:opacity-100 transition-opacity rounded-2xl" />
              <div className="relative z-10">
                <div className="flex items-center gap-2 mb-3 text-muted-foreground group-hover:text-primary transition-colors">
                  <Activity className="h-4 w-4" />
                  <span className="text-xs font-semibold uppercase tracking-wider">System Uptime</span>
                </div>
                <div className="flex items-baseline gap-2">
                  <div className="text-4xl font-black tracking-tighter text-foreground">99.9%</div>
                  <span className="text-emerald-500 text-xs font-bold bg-emerald-500/10 px-2 py-0.5 rounded-full">↑ SLA</span>
                </div>
              </div>
            </div>

            {/* Stat 2 */}
            <div className="group relative rounded-2xl bg-black/20 hover:bg-black/40 border border-white/5 hover:border-blue-500/30 p-5 backdrop-blur-md transition-all duration-300 hover:-translate-y-1 shadow-2xl">
              <div className="absolute inset-0 bg-gradient-to-br from-blue-500/10 to-transparent opacity-0 group-hover:opacity-100 transition-opacity rounded-2xl" />
              <div className="relative z-10">
                <div className="flex items-center gap-2 mb-3 text-muted-foreground group-hover:text-blue-500 transition-colors">
                  <Target className="h-4 w-4" />
                  <span className="text-xs font-semibold uppercase tracking-wider">Inference Accuracy</span>
                </div>
                <div className="flex items-baseline gap-2">
                  <div className="text-4xl font-black tracking-tighter text-foreground">98.2%</div>
                  <span className="text-emerald-500 text-xs font-bold bg-emerald-500/10 px-2 py-0.5 rounded-full">+4.1%</span>
                </div>
              </div>
            </div>

            {/* Stat 3 - Spans full width */}
            <div className="col-span-2 group relative rounded-2xl bg-black/20 hover:bg-black/40 border border-white/5 hover:border-indigo-500/30 p-5 backdrop-blur-md transition-all duration-300 hover:-translate-y-1 shadow-2xl flex items-center justify-between">
              <div className="absolute inset-0 bg-gradient-to-br from-indigo-500/10 to-transparent opacity-0 group-hover:opacity-100 transition-opacity rounded-2xl" />
              <div className="relative z-10 flex-1">
                <div className="flex items-center gap-2 mb-2 text-muted-foreground group-hover:text-indigo-400 transition-colors">
                  <Zap className="h-4 w-4" />
                  <span className="text-xs font-semibold uppercase tracking-wider">Threat Neutralization Speed</span>
                </div>
                <div className="flex items-baseline gap-2">
                  <div className="text-3xl font-black tracking-tighter text-foreground">&lt; 1.2s</div>
                  <span className="text-muted-foreground text-sm font-medium">avg. processing latency</span>
                </div>
              </div>
              <div className="h-12 w-12 rounded-full border border-indigo-500/30 bg-indigo-500/10 flex items-center justify-center shrink-0">
                <ShieldCheck className="h-6 w-6 text-indigo-400" />
              </div>
            </div>

          </div>
        </div>
      </div>

      {/* Right side - Auth Form */}
      <div className="flex w-full items-center justify-center p-8 lg:w-1/2 relative z-10 bg-background/50 backdrop-blur-xl border-l border-white/5 shadow-2xl">
        <div className="w-full max-w-md">
          {/* Mobile logo */}
          <div className="mb-8 flex items-center gap-3 lg:hidden">
            <div className="flex h-12 w-12 items-center justify-center rounded-xl bg-black/40 border border-white/10 backdrop-blur-md shadow-xl overflow-hidden p-1">
              <img src="/logo.png" alt="VisionGuard Logo" className="w-full h-full object-contain" />
            </div>
            <div>
              <h1 className="text-2xl font-bold text-foreground">VisionGuard AI</h1>
              <p className="text-xs text-emerald-500 uppercase tracking-widest font-bold">System Active</p>
            </div>
          </div>

          <Outlet />
        </div>
      </div>
    </div>
  );
}
