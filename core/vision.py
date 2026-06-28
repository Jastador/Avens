import cv2
import screen_brightness_control as sbc
import mediapipe as mp
from mediapipe.tasks import python
from mediapipe.tasks.python import vision
import urllib.request
import os
import math
import sys
import time
import threading

# Ensure it can find the automation folder
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from automation.commands import force_volume_change

# Global flag to control the camera thread
vision_active = False

def download_model():
    """Auto-downloads the modern Hand Tracking AI model if it's missing."""
    model_path = os.path.join(os.path.dirname(__file__), 'hand_landmarker.task')
    if not os.path.exists(model_path):
        print("⏳ Downloading modern MediaPipe Hand tracking model...")
        url = "https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task"
        urllib.request.urlretrieve(url, model_path)
    return model_path

def draw_manual_skeleton(img, landmarks):
    """Manually draws the hand skeleton to bypass the broken mp.solutions bug!"""
    h, w, _ = img.shape
    # Define how the joints connect to each other
    connections = [
        (0, 1), (1, 2), (2, 3), (3, 4),        # Thumb
        (0, 5), (5, 6), (6, 7), (7, 8),        # Index
        (5, 9), (9, 10), (10, 11), (11, 12),   # Middle
        (9, 13), (13, 14), (14, 15), (15, 16), # Ring
        (13, 17), (17, 18), (18, 19), (19, 20),# Pinky
        (0, 17)                                # Base connection
    ]
    # Convert normalized landmarks to pixel coordinates
    points = []
    for lm in landmarks:
        px, py = int(lm.x * w), int(lm.y * h)
        points.append((px, py))
        # Draw the joint dots
        cv2.circle(img, (px, py), 5, (0, 255, 255), cv2.FILLED)
    # Draw the connecting lines
    for connection in connections:
        start_idx, end_idx = connection
        if start_idx < len(points) and end_idx < len(points):
            cv2.line(img, points[start_idx], points[end_idx], (0, 25, 0), 2)

def run_vision_loop():
    global vision_active
    model_path = download_model()
    base_options = python.BaseOptions(model_asset_path=model_path)
    options = vision.HandLandmarkerOptions(
        base_options=base_options,
        num_hands=1,
        min_hand_detection_confidence=0.7,
        min_hand_presence_confidence=0.7,
        min_tracking_confidence=0.7,
        running_mode=vision.RunningMode.VIDEO
    )
    detector = vision.HandLandmarker.create_from_options(options)
    cap = cv2.VideoCapture(0)
    print("👁️ Optical Sensors Online.")
    last_gesture_time = 0
    last_timestamp_ms = 0
    
    while vision_active:
        success, img = cap.read()
        if not success: continue
        img = cv2.flip(img, 1)
        rgb_img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb_img)
        current_timestamp_ms = int(time.time() * 1000)
        
        if current_timestamp_ms <= last_timestamp_ms:
            current_timestamp_ms = last_timestamp_ms + 1
        last_timestamp_ms = current_timestamp_ms
        
        detection_result = detector.detect_for_video(mp_image, current_timestamp_ms)
        if detection_result.hand_landmarks:
            for hand_landmarks in detection_result.hand_landmarks:
                # 🎨 DRAW THE CUSTOM SKELETON (No broken modules needed!)
                draw_manual_skeleton(img, hand_landmarks)
                # Get coordinates
                thumb = hand_landmarks[4]
                index = hand_landmarks[8]
                middle = hand_landmarks[12]
                ring = hand_landmarks[16]
                
                thumb_x, thumb_y = int(thumb.x * img.shape[1]), int(thumb.y * img.shape[0])
                index_x, index_y = int(index.x * img.shape[1]), int(index.y * img.shape[0])
                middle_x, middle_y = int(middle.x * img.shape[1]), int(middle.y * img.shape[0])
                ring_x, ring_y = int(ring.x * img.shape[1]), int(ring.y * img.shape[0])
                
                # Math: Calculate distances
                vol_distance = math.hypot(index_x - thumb_x, index_y - thumb_y)
                bright_distance = math.hypot(middle_x - thumb_x, middle_y - thumb_y)
                
                # 🔥 THE FIST CHECK: Are the other fingers open?
                is_fist = False
                if math.hypot(ring_x - thumb_x, ring_y - thumb_y) < 50:
                    is_fist = True
                current_time = time.time()
                
                # Only trigger gestures if it's NOT a closed fist
                if not is_fist:
                    # 🚀 GESTURE LOGIC: VOLUME DOWN (Thumb + Index Pinch)
                    if vol_distance < 30 and bright_distance > 50:
                        cv2.putText(img, 'VOL DOWN', (50, 50), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 3)
                        if (current_time - last_gesture_time > 0.3):
                            force_volume_change("down", 2)
                            last_gesture_time = current_time
                    # 🚀 GESTURE LOGIC: VOLUME UP (Thumb + Index Wide Open)
                    elif vol_distance > 150 and bright_distance > 50:
                        cv2.putText(img, 'VOL UP', (50, 50), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 3)
                        if (current_time - last_gesture_time > 0.3):
                            force_volume_change("up", 2)
                            last_gesture_time = current_time
                    # 🚀 GESTURE LOGIC: BRIGHTNESS DOWN (Thumb + Middle Pinch)
                    elif bright_distance < 30 and vol_distance > 50:
                        cv2.putText(img, 'BRIGHT DOWN', (50, 100), cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 0, 0), 3)
                        if (current_time - last_gesture_time > 0.3):
                            try:
                                current_brightness = sbc.get_brightness()[0]
                                sbc.set_brightness(max(0, current_brightness - 10))
                            except: pass
                            last_gesture_time = current_time
                    # 🚀 GESTURE LOGIC: BRIGHTNESS UP (Thumb + Middle Wide Open)
                    elif bright_distance > 150 and vol_distance < 100:
                        cv2.putText(img, 'BRIGHT UP', (50, 100), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 255), 3)
                        if (current_time - last_gesture_time > 0.3):
                            try:
                                current_brightness = sbc.get_brightness()[0]
                                sbc.set_brightness(min(100, current_brightness + 10))
                            except: pass
                            last_gesture_time = current_time
                            
        cv2.imshow("Avens Vision", img)
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break
            
    # Cleanup when the loop is stopped safely
    try: detector.close()  # 🔥 THIS PREVENTS THE THREAD CRASH
    except: pass
    cap.release()
    cv2.destroyAllWindows()
    print("👁️ Optical Sensors Offline.")

def start_vision():
    """Starts the camera thread if it isn't already running."""
    global vision_active
    if not vision_active:
        vision_active = True
        threading.Thread(target=run_vision_loop, daemon=True).start()

def stop_vision():
    """Signals the camera thread to shut down."""
    global vision_active
    vision_active = False

if __name__ == "__main__":
    vision_active = True
    run_vision_loop()