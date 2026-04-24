"""
VisionGuard AI - Test Video Player

Simple script to stream/play the test video file.
Useful for verifying the video before running full pipeline.

Usage:
    python scripts/play_test_video.py
"""

import cv2
import os
import sys
import time


def play_video(video_path: str, fps: int = 30, loop: bool = True):
    """
    Play video file in a window.
    
    Args:
        video_path: Path to video file
        fps: Playback frames per second
        loop: Loop the video
    """
    if not os.path.exists(video_path):
        print(f"Error: Video not found: {video_path}")
        sys.exit(1)
    
    print(f"Opening video: {video_path}")
    
    cap = cv2.VideoCapture(video_path)
    
    if not cap.isOpened():
        print("Error: Could not open video")
        sys.exit(1)
    
    # Get video info
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    video_fps = cap.get(cv2.CAP_PROP_FPS)
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    
    print(f"Video Info:")
    print(f"  - Resolution: {width}x{height}")
    print(f"  - FPS: {video_fps}")
    print(f"  - Total Frames: {total_frames}")
    print(f"  - Duration: {total_frames / video_fps:.1f} seconds")
    print()
    print("Playing... Press 'q' to quit, SPACE to pause")
    
    delay = int(1000 / fps)
    frame_count = 0
    paused = False
    
    while True:
        if not paused:
            ret, frame = cap.read()
            
            if not ret:
                if loop:
                    cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                    continue
                else:
                    break
            
            frame_count += 1
            
            # Add frame info overlay
            cv2.putText(frame, f"Frame: {frame_count}/{total_frames}", 
                       (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
            cv2.putText(frame, "Press 'q' to quit, SPACE to pause",
                       (10, height - 20), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
            
            cv2.imshow("VisionGuard AI - Test Video", frame)
        
        key = cv2.waitKey(delay if not paused else 100) & 0xFF
        
        if key == ord('q'):
            break
        elif key == ord(' '):
            paused = not paused
            print("Paused" if paused else "Resumed")
    
    cap.release()
    cv2.destroyAllWindows()
    print("Video playback ended.")


def main():
    # Find video file
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(script_dir)
    
    video_path = os.path.join(project_root, "test-video.mp4")
    
    if not os.path.exists(video_path):
        # Try current directory
        video_path = "test-video.mp4"
    
    play_video(video_path, fps=30, loop=True)


if __name__ == "__main__":
    main()
