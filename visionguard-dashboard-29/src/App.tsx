import { Toaster } from "@/components/ui/toaster";
import { Toaster as Sonner } from "@/components/ui/sonner";
import { TooltipProvider } from "@/components/ui/tooltip";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { AuthProvider } from "@/contexts/AuthContext";
import { DashboardLayout } from "@/components/layout/DashboardLayout";
import { AuthLayout } from "@/components/layout/AuthLayout";

// Auth Pages
import Login from "@/pages/auth/Login";
import Register from "@/pages/auth/Register";

// Dashboard Pages
import Dashboard from "@/pages/Dashboard";
import LiveMonitoring from "@/pages/LiveMonitoring";
import Incidents from "@/pages/Incidents";
import Analytics from "@/pages/Analytics";
import Cameras from "@/pages/Cameras";
import Zones from "@/pages/Zones";
import Users from "@/pages/Users";
import Settings from "@/pages/Settings";
import NotFound from "@/pages/NotFound";

const queryClient = new QueryClient();

const App = () => (
  <QueryClientProvider client={queryClient}>
    <AuthProvider>
      <TooltipProvider>
        <Toaster />
        <Sonner />
        <BrowserRouter>
          <Routes>
            {/* Root redirect */}
            <Route path="/" element={<Navigate to="/dashboard" replace />} />

            {/* Auth routes */}
            <Route path="/auth" element={<AuthLayout />}>
              <Route path="login" element={<Login />} />
              <Route path="register" element={<Register />} />
            </Route>

            {/* Dashboard routes */}
            <Route element={<DashboardLayout />}>
              <Route path="/dashboard" element={<Dashboard />} />
              <Route path="/monitoring" element={<LiveMonitoring />} />
              <Route path="/incidents" element={<Incidents />} />
              <Route path="/analytics" element={<Analytics />} />
              <Route path="/cameras" element={<Cameras />} />
              <Route path="/zones" element={<Zones />} />
              <Route path="/users" element={<Users />} />
              <Route path="/settings" element={<Settings />} />
            </Route>

            {/* Catch-all */}
            <Route path="*" element={<NotFound />} />
          </Routes>
        </BrowserRouter>
      </TooltipProvider>
    </AuthProvider>
  </QueryClientProvider>
);

export default App;
