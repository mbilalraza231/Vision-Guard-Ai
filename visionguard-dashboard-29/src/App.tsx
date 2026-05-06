import { Toaster } from "@/components/ui/toaster";
import { Toaster as Sonner } from "@/components/ui/sonner";
import { TooltipProvider } from "@/components/ui/tooltip";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { AuthProvider } from "@/contexts/AuthContext";
import { DashboardLayout } from "@/components/layout/DashboardLayout";
import { AuthLayout } from "@/components/layout/AuthLayout";
import { ProtectedRoute } from "@/components/auth/ProtectedRoute";

// Auth Pages
import Login from "@/pages/auth/Login";
import Register from "@/pages/auth/Register";
import ForgotPassword from "@/pages/auth/ForgotPassword";
import UpdatePassword from "@/pages/auth/UpdatePassword";

// Dashboard Pages
import Dashboard from "@/pages/Dashboard";
import LiveMonitoring from "@/pages/LiveMonitoring";
import Incidents from "@/pages/Incidents";
import Analytics from "@/pages/Analytics";
import Cameras from "@/pages/Cameras";
import Zones from "@/pages/Zones";
import Users from "@/pages/Users";
import Settings from "@/pages/Settings";
import Profile from "@/pages/Profile";
import IncidentDetails from "@/pages/IncidentDetails";
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
              <Route path="forgot-password" element={<ForgotPassword />} />
              <Route path="update-password" element={<UpdatePassword />} />
            </Route>

            {/* Dashboard routes */}
            <Route element={<DashboardLayout />}>
              <Route path="/dashboard" element={<Dashboard />} />
              <Route path="/monitoring" element={<LiveMonitoring />} />
              <Route path="/incidents" element={<Incidents />} />
              
              <Route 
                path="/analytics" 
                element={
                  <ProtectedRoute requiredRoles={['admin', 'manager']}>
                    <Analytics />
                  </ProtectedRoute>
                } 
              />
              <Route 
                path="/cameras" 
                element={
                  <ProtectedRoute requiredRoles={['admin', 'manager']}>
                    <Cameras />
                  </ProtectedRoute>
                } 
              />
              <Route 
                path="/zones" 
                element={
                  <ProtectedRoute requiredRoles={['admin', 'manager']}>
                    <Zones />
                  </ProtectedRoute>
                } 
              />
              <Route path="/users" element={<ProtectedRoute requiredRoles={['admin']}><Users /></ProtectedRoute>} />
              <Route path="/settings" element={<ProtectedRoute requiredRoles={['admin']}><Settings /></ProtectedRoute>} />
              <Route path="/profile" element={<Profile />} />
              <Route path="/incidents/:id" element={<IncidentDetails />} />
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
