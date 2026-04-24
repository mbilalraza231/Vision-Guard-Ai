import { API_ENDPOINTS } from '@/config/api';
import { apiService, tokenStorage } from './api.service';
import type { User, LoginCredentials, AuthTokens, ApiResponse } from '@/types';

interface LoginResponse {
  user: User;
  tokens: AuthTokens;
}

class AuthService {
  async login(credentials: LoginCredentials): Promise<ApiResponse<LoginResponse>> {
    const response = await apiService.post<LoginResponse>(
      API_ENDPOINTS.auth.login,
      credentials
    );

    if (response.success && response.data) {
      const { tokens } = response.data;
      tokenStorage.setAccessToken(tokens.accessToken);
      if (tokens.refreshToken) {
        tokenStorage.setRefreshToken(tokens.refreshToken);
      }
    }

    return response;
  }

  async logout(): Promise<void> {
    try {
      await apiService.post(API_ENDPOINTS.auth.logout);
    } catch {
      // Continue with local logout even if API call fails
    } finally {
      tokenStorage.clearTokens();
    }
  }

  async getCurrentUser(): Promise<ApiResponse<User>> {
    return apiService.get<User>(API_ENDPOINTS.auth.me);
  }

  async refreshTokens(): Promise<ApiResponse<AuthTokens>> {
    const refreshToken = tokenStorage.getRefreshToken();
    if (!refreshToken) {
      return {
        data: null as unknown as AuthTokens,
        success: false,
        error: 'No refresh token available',
      };
    }

    const response = await apiService.post<AuthTokens>(API_ENDPOINTS.auth.refresh, {
      refreshToken,
    });

    if (response.success && response.data) {
      tokenStorage.setAccessToken(response.data.accessToken);
      if (response.data.refreshToken) {
        tokenStorage.setRefreshToken(response.data.refreshToken);
      }
    }

    return response;
  }

  isAuthenticated(): boolean {
    return !!tokenStorage.getAccessToken();
  }

  getAccessToken(): string | null {
    return tokenStorage.getAccessToken();
  }
}

export const authService = new AuthService();
