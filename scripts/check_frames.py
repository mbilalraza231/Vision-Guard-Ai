
import os
import sys
import numpy as np
import struct

SHARED_DIR = "/shared-frames"

def check_frames():
    files = [f for f in os.listdir(SHARED_DIR) if not f.endswith('.tmp')]
    print(f"Found {len(files)} files in {SHARED_DIR}")
    
    for f in files[:5]:
        path = os.path.join(SHARED_DIR, f)
        try:
            with open(path, 'rb') as f_in:
                header = f_in.read(16)
                h, w, c, dt = struct.unpack('IIII', header)
                data = f_in.read()
                print(f"File: {path}, Header: {h}x{w}x{c}, dtype={dt}, bytes={len(data)}")
                
                # Try to reconstruct
                if dt == 0: # uint8
                    frame = np.frombuffer(data, dtype=np.uint8)
                    if len(frame) == h*w*c:
                        frame = frame.reshape(h, w, c)
                        print(f"  Frame Mean: {frame.mean():.2f}, Std: {frame.std():.2f}")
                    else:
                        print(f"  SIZE MISMATCH: expected {h*w*c}, got {len(frame)}")
        except Exception as e:
            print(f"  Error reading {path}: {e}")

if __name__ == "__main__":
    check_frames()
