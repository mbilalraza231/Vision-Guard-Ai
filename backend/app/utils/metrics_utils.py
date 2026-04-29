import os
import time
import json
import psutil
import threading
import socket
from typing import Dict, Any, List

class MetricsReporter:
    """
    Reports process resource usage to Redis.
    Used for 'Project Only' metrics.
    """
    def __init__(self, redis_client, service_name: str, interval: int = 5):
        self.redis = redis_client
        self.service_name = service_name
        self.interval = interval
        self.instance_id = socket.gethostname()
        self.key = f"vg:metrics:{service_name}:{self.instance_id}"
        self._stop_event = threading.Event()
        self._thread = None
        self.process = psutil.Process(os.getpid())

    def get_metrics(self) -> Dict[str, Any]:
        """Calculate metrics for the current process and all its children."""
        try:
            # Memory in GB
            memory_bytes = self.process.memory_info().rss
            for child in self.process.children(recursive=True):
                try:
                    memory_bytes += child.memory_info().rss
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass
            
            # CPU Percentage (relative to one core)
            # We call it twice or use interval to get a stable value
            # Use a 0.1s interval to get a real-time sample without blocking too long
            cpu_percent = self.process.cpu_percent(interval=0.1)
            for child in self.process.children(recursive=True):
                try:
                    cpu_percent += child.cpu_percent(interval=0.5)
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass

            return {
                "service": self.service_name,
                "instance": self.instance_id,
                "cpu_percent": round(cpu_percent, 2),
                "memory_gb": round(memory_bytes / (1024 ** 3), 4),
                "timestamp": time.time()
            }
        except Exception:
            return {}

    def _run(self):
        # Initial call to cpu_percent to initialize
        self.process.cpu_percent(interval=None)
        
        while not self._stop_event.is_set():
            metrics = self.get_metrics()
            if metrics:
                try:
                    # Write to Redis with a TTL of 15 seconds
                    self.redis.setex(self.key, 15, json.dumps(metrics))
                except Exception:
                    pass
            time.sleep(self.interval)

    def start(self):
        """Start reporting in a background thread."""
        if self._thread is None or not self._thread.is_alive():
            self._stop_event.clear()
            self._thread = threading.Thread(target=self._run, daemon=True)
            self._thread.start()

    def stop(self):
        """Stop reporting."""
        if self._thread:
            self._stop_event.set()
            self._thread.join(timeout=2)

def aggregate_project_metrics(redis_client) -> Dict[str, float]:
    """Aggregate metrics from all active services in Redis."""
    total_cpu = 0.0
    total_memory = 0.0
    
    try:
        keys = redis_client.keys("vg:metrics:*")
        for key in keys:
            data = redis_client.get(key)
            if data:
                metrics = json.loads(data)
                total_cpu += metrics.get("cpu_percent", 0.0)
                total_memory += metrics.get("memory_gb", 0.0)
    except Exception:
        pass
        
    return {
        "cpu_usage": round(total_cpu, 2),
        "memory_used_gb": round(total_memory, 3)
    }

def check_service_liveness(redis_client, service_name: str) -> bool:
    """
    Check if a specific service has an active heartbeat in Redis.
    
    Args:
        redis_client: Redis client instance
        service_name: Name of the service (e.g., 'ecs', 'camera')
        
    Returns:
        True if at least one instance of the service is active
    """
    try:
        keys = redis_client.keys(f"vg:metrics:{service_name}:*")
        return len(keys) > 0
    except Exception:
        return False
