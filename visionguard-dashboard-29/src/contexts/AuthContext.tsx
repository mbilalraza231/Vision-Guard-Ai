import { createContext, useContext, useState, type ReactNode } from 'react';
import type { User, AuthState, LoginCredentials } from '@/types';

interface AuthContextType extends AuthState {
  login: (credentials: LoginCredentials) => Promise<boolean>;
  logout: () => Promise<void>;
  checkAuth: () => Promise<void>;
}

const AuthContext = createContext<AuthContextType | null>(null);

// Hardcoded demo user — backend has no auth endpoints
const DEMO_USER: User = {
  id: '1',
  name: 'Admin',
  email: 'admin@visionguard.ai',
  role: 'admin',
  status: 'active',
  createdAt: new Date().toISOString(),
};

export function AuthProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<AuthState>({
    user: DEMO_USER,
    isAuthenticated: true,
    isLoading: false,
  });

  const checkAuth = async () => {
    // No auth endpoints on backend — always authenticated as demo user
    setState({
      user: DEMO_USER,
      isAuthenticated: true,
      isLoading: false,
    });
  };

  const login = async (_credentials: LoginCredentials): Promise<boolean> => {
    // No auth — immediately authenticate
    setState({
      user: DEMO_USER,
      isAuthenticated: true,
      isLoading: false,
    });
    return true;
  };

  const logout = async () => {
    setState({
      user: null,
      isAuthenticated: false,
      isLoading: false,
    });
  };

  return (
    <AuthContext.Provider
      value={{
        ...state,
        login,
        logout,
        checkAuth,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
}
