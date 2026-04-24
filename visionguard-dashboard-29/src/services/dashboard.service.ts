import { API_ENDPOINTS } from '@/config/api';
import { apiService } from './api.service';
import type { DashboardStats, SystemMetrics, Incident, ApiResponse } from '@/types';

class DashboardService {
  async getStats(): Promise<ApiResponse<DashboardStats>> {
    return apiService.get<DashboardStats>(API_ENDPOINTS.dashboard.stats);
  }

  async getSystemMetrics(): Promise<ApiResponse<SystemMetrics>> {
    return apiService.get<SystemMetrics>(API_ENDPOINTS.dashboard.systemMetrics);
  }

  async getRecentIncidents(limit = 5): Promise<ApiResponse<Incident[]>> {
    return apiService.get<Incident[]>(API_ENDPOINTS.dashboard.recentIncidents, {
      limit: limit.toString(),
    });
  }
}

export const dashboardService = new DashboardService();
