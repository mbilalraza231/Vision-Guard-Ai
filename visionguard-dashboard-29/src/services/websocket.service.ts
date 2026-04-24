import { API_CONFIG, buildWsUrl } from '@/config/api';
import type { WebSocketEvent } from '@/types';

type EventHandler = (event: WebSocketEvent) => void;

class WebSocketService {
  private socket: WebSocket | null = null;
  private eventHandlers: Map<string, Set<EventHandler>> = new Map();
  private reconnectAttempts = 0;
  private maxReconnectAttempts = 5;
  private reconnectDelay = 1000;
  private isConnecting = false;

  connect(): void {
    if (this.socket?.readyState === WebSocket.OPEN || this.isConnecting) {
      return;
    }

    this.isConnecting = true;

    try {
      this.socket = new WebSocket(buildWsUrl());

      this.socket.onopen = () => {
        console.log('[WebSocket] Connected');
        this.isConnecting = false;
        this.reconnectAttempts = 0;
      };

      this.socket.onmessage = (event) => {
        try {
          const data: WebSocketEvent = JSON.parse(event.data);
          this.notifyHandlers(data.type, data);
        } catch (error) {
          console.error('[WebSocket] Failed to parse message:', error);
        }
      };

      this.socket.onclose = () => {
        console.log('[WebSocket] Disconnected');
        this.isConnecting = false;
        this.attemptReconnect();
      };

      this.socket.onerror = (error) => {
        console.error('[WebSocket] Error:', error);
        this.isConnecting = false;
      };
    } catch (error) {
      console.error('[WebSocket] Failed to connect:', error);
      this.isConnecting = false;
    }
  }

  disconnect(): void {
    if (this.socket) {
      this.socket.close();
      this.socket = null;
    }
    this.reconnectAttempts = this.maxReconnectAttempts; // Prevent reconnection
  }

  private attemptReconnect(): void {
    if (this.reconnectAttempts >= this.maxReconnectAttempts) {
      console.log('[WebSocket] Max reconnection attempts reached');
      return;
    }

    this.reconnectAttempts++;
    const delay = this.reconnectDelay * Math.pow(2, this.reconnectAttempts - 1);

    console.log(`[WebSocket] Reconnecting in ${delay}ms (attempt ${this.reconnectAttempts})`);

    setTimeout(() => {
      this.connect();
    }, delay);
  }

  subscribe(eventType: string, handler: EventHandler): () => void {
    if (!this.eventHandlers.has(eventType)) {
      this.eventHandlers.set(eventType, new Set());
    }

    this.eventHandlers.get(eventType)!.add(handler);

    // Return unsubscribe function
    return () => {
      this.eventHandlers.get(eventType)?.delete(handler);
    };
  }

  private notifyHandlers(eventType: string, event: WebSocketEvent): void {
    // Notify specific type handlers
    this.eventHandlers.get(eventType)?.forEach((handler) => handler(event));

    // Notify wildcard handlers
    this.eventHandlers.get('*')?.forEach((handler) => handler(event));
  }

  send(data: unknown): void {
    if (this.socket?.readyState === WebSocket.OPEN) {
      this.socket.send(JSON.stringify(data));
    } else {
      console.warn('[WebSocket] Cannot send - not connected');
    }
  }

  get isConnected(): boolean {
    return this.socket?.readyState === WebSocket.OPEN;
  }
}

export const wsService = new WebSocketService();
