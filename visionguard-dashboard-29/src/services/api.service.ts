import { API_CONFIG, buildApiUrl } from '@/config/api';
import type { ApiResponse } from '@/types';

// Token storage abstraction - can be swapped for more secure storage
const tokenStorage = {
  getAccessToken: (): string | null => {
    return sessionStorage.getItem('access_token');
  },
  setAccessToken: (token: string): void => {
    sessionStorage.setItem('access_token', token);
  },
  getRefreshToken: (): string | null => {
    return localStorage.getItem('refresh_token');
  },
  setRefreshToken: (token: string): void => {
    localStorage.setItem('refresh_token', token);
  },
  clearTokens: (): void => {
    sessionStorage.removeItem('access_token');
    localStorage.removeItem('refresh_token');
  },
};

// Request interceptor type
type RequestInterceptor = (config: RequestInit) => RequestInit;

// Response interceptor type
type ResponseInterceptor = (response: Response) => Response | Promise<Response>;

class ApiService {
  private requestInterceptors: RequestInterceptor[] = [];
  private responseInterceptors: ResponseInterceptor[] = [];

  constructor() {
    // Add default auth interceptor
    this.addRequestInterceptor((config) => {
      const token = tokenStorage.getAccessToken();
      if (token) {
        const headers = new Headers(config.headers);
        headers.set('Authorization', `Bearer ${token}`);
        return { ...config, headers };
      }
      return config;
    });
  }

  addRequestInterceptor(interceptor: RequestInterceptor): void {
    this.requestInterceptors.push(interceptor);
  }

  addResponseInterceptor(interceptor: ResponseInterceptor): void {
    this.responseInterceptors.push(interceptor);
  }

  private async request<T>(
    endpoint: string,
    options: RequestInit = {}
  ): Promise<ApiResponse<T>> {
    const url = buildApiUrl(endpoint);

    // Apply request interceptors
    let config: RequestInit = {
      ...options,
      headers: {
        'Content-Type': 'application/json',
        ...options.headers,
      },
    };

    for (const interceptor of this.requestInterceptors) {
      config = interceptor(config);
    }

    // Create abort controller for timeout
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), API_CONFIG.timeout);

    try {
      let response = await fetch(url, {
        ...config,
        signal: controller.signal,
      });

      clearTimeout(timeoutId);

      // Apply response interceptors
      for (const interceptor of this.responseInterceptors) {
        response = await interceptor(response);
      }

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        return {
          data: null as T,
          success: false,
          error: errorData.message || `HTTP Error: ${response.status}`,
        };
      }

      const data = await response.json();
      return {
        data,
        success: true,
      };
    } catch (error) {
      clearTimeout(timeoutId);

      if (error instanceof Error) {
        if (error.name === 'AbortError') {
          return {
            data: null as T,
            success: false,
            error: 'Request timeout',
          };
        }
        return {
          data: null as T,
          success: false,
          error: error.message,
        };
      }

      return {
        data: null as T,
        success: false,
        error: 'An unknown error occurred',
      };
    }
  }

  async get<T>(endpoint: string, params?: Record<string, string>): Promise<ApiResponse<T>> {
    const url = params
      ? `${endpoint}?${new URLSearchParams(params).toString()}`
      : endpoint;
    return this.request<T>(url, { method: 'GET' });
  }

  async getData<T>(endpoint: string, params?: Record<string, string>): Promise<T> {
    const response = await this.get<T>(endpoint, params);
    if (!response.success || response.data == null) {
      throw new Error(response.error || 'Request failed');
    }
    return response.data;
  }

  async post<T>(endpoint: string, data?: unknown): Promise<ApiResponse<T>> {
    return this.request<T>(endpoint, {
      method: 'POST',
      body: data ? JSON.stringify(data) : undefined,
    });
  }

  async postData<T>(endpoint: string, data?: unknown): Promise<T> {
    const response = await this.post<T>(endpoint, data);
    if (!response.success || response.data == null) {
      throw new Error(response.error || 'Request failed');
    }
    return response.data;
  }

  async put<T>(endpoint: string, data?: unknown): Promise<ApiResponse<T>> {
    return this.request<T>(endpoint, {
      method: 'PUT',
      body: data ? JSON.stringify(data) : undefined,
    });
  }

  async putData<T>(endpoint: string, data?: unknown): Promise<T> {
    const response = await this.put<T>(endpoint, data);
    if (!response.success || response.data == null) {
      throw new Error(response.error || 'Request failed');
    }
    return response.data;
  }

  async patch<T>(endpoint: string, data?: unknown): Promise<ApiResponse<T>> {
    return this.request<T>(endpoint, {
      method: 'PATCH',
      body: data ? JSON.stringify(data) : undefined,
    });
  }

  async patchData<T>(endpoint: string, data?: unknown): Promise<T> {
    const response = await this.patch<T>(endpoint, data);
    if (!response.success || response.data == null) {
      throw new Error(response.error || 'Request failed');
    }
    return response.data;
  }

  async delete<T>(endpoint: string): Promise<ApiResponse<T>> {
    return this.request<T>(endpoint, { method: 'DELETE' });
  }

  async deleteData<T>(endpoint: string): Promise<T> {
    const response = await this.delete<T>(endpoint);
    if (!response.success || response.data == null) {
      throw new Error(response.error || 'Request failed');
    }
    return response.data;
  }
}

// Export singleton instance
export const apiService = new ApiService();

// Export token storage for auth service
export { tokenStorage };
