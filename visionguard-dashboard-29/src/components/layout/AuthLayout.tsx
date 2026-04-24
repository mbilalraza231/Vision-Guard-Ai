import { Outlet } from 'react-router-dom';
import { Camera } from 'lucide-react';

export function AuthLayout() {
  return (
    <div className="flex min-h-screen bg-background">
      {/* Left side - Branding */}
      <div className="hidden w-1/2 flex-col justify-center bg-gradient-to-br from-primary/20 via-background to-background p-12 lg:flex">
        <div className="flex items-center gap-3 mb-8">
          <div className="flex h-12 w-12 items-center justify-center rounded-xl bg-primary/10">
            <Camera className="h-7 w-7 text-primary" />
          </div>
          <div>
            <h1 className="text-2xl font-bold text-foreground">VisionGuard AI</h1>
            <p className="text-sm text-muted-foreground">v2.0</p>
          </div>
        </div>
        
        <h2 className="text-4xl font-bold leading-tight mb-4">
          AI-Powered
          <br />
          <span className="text-primary">Real-Time Surveillance</span>
        </h2>
        
        <p className="text-lg text-muted-foreground max-w-md">
          Advanced incident detection and monitoring system with 
          real-time AI analysis and intelligent alerting.
        </p>

        <div className="mt-12 grid grid-cols-2 gap-6">
          <div className="rounded-xl bg-card/50 p-4 border border-border">
            <div className="text-3xl font-bold text-primary mb-1">99.4%</div>
            <div className="text-sm text-muted-foreground">System Uptime</div>
          </div>
          <div className="rounded-xl bg-card/50 p-4 border border-border">
            <div className="text-3xl font-bold text-primary mb-1">92%</div>
            <div className="text-sm text-muted-foreground">Detection Accuracy</div>
          </div>
          <div className="rounded-xl bg-card/50 p-4 border border-border">
            <div className="text-3xl font-bold text-primary mb-1">2.3min</div>
            <div className="text-sm text-muted-foreground">Avg Response Time</div>
          </div>
          <div className="rounded-xl bg-card/50 p-4 border border-border">
            <div className="text-3xl font-bold text-primary mb-1">4.2%</div>
            <div className="text-sm text-muted-foreground">False Positive Rate</div>
          </div>
        </div>
      </div>

      {/* Right side - Auth Form */}
      <div className="flex w-full items-center justify-center p-8 lg:w-1/2">
        <div className="w-full max-w-md">
          {/* Mobile logo */}
          <div className="mb-8 flex items-center gap-3 lg:hidden">
            <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-primary/10">
              <Camera className="h-5 w-5 text-primary" />
            </div>
            <div>
              <h1 className="text-xl font-bold text-foreground">VisionGuard AI</h1>
              <p className="text-xs text-muted-foreground">v2.0</p>
            </div>
          </div>

          <Outlet />
        </div>
      </div>
    </div>
  );
}
