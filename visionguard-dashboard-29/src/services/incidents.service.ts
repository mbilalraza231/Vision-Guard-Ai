import { API_ENDPOINTS } from '@/config/api';
import { apiService } from './api.service';
import type { Incident, IncidentFilters, ApiResponse, PaginatedResponse } from '@/types';

class IncidentsService {
  async getIncidents(
    filters?: IncidentFilters,
    page = 1,
    pageSize = 20
  ): Promise<ApiResponse<PaginatedResponse<Incident>>> {
    const params: Record<string, string> = {
      page: page.toString(),
      pageSize: pageSize.toString(),
    };

    if (filters) {
      if (filters.severity && filters.severity !== 'all') {
        params.severity = filters.severity;
      }
      if (filters.type && filters.type !== 'all') {
        params.type = filters.type;
      }
      if (filters.status && filters.status !== 'all') {
        params.status = filters.status;
      }
      if (filters.camera && filters.camera !== 'all') {
        params.camera = filters.camera;
      }
      if (filters.dateRange) {
        params.startDate = filters.dateRange.start.toISOString();
        params.endDate = filters.dateRange.end.toISOString();
      }
    }

    return apiService.get<PaginatedResponse<Incident>>(API_ENDPOINTS.incidents.list, params);
  }

  async getIncidentById(id: string): Promise<ApiResponse<Incident>> {
    return apiService.get<Incident>(API_ENDPOINTS.incidents.byId(id));
  }

  async updateIncidentStatus(
    id: string,
    status: Incident['status']
  ): Promise<ApiResponse<Incident>> {
    return apiService.patch<Incident>(API_ENDPOINTS.incidents.update(id), { status });
  }

  async exportIncidents(filters?: IncidentFilters): Promise<ApiResponse<Blob>> {
    const params: Record<string, string> = {};

    if (filters) {
      if (filters.severity && filters.severity !== 'all') {
        params.severity = filters.severity;
      }
      if (filters.type && filters.type !== 'all') {
        params.type = filters.type;
      }
      if (filters.status && filters.status !== 'all') {
        params.status = filters.status;
      }
    }

    return apiService.get<Blob>(API_ENDPOINTS.incidents.export, params);
  }
}

export const incidentsService = new IncidentsService();
