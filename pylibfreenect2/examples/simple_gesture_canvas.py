#!/usr/bin/env python
"""
Simple Gesture-Controlled Canvas - Basic MS Paint Style
==========================================
A minimalist full-screen drawing application controlled by hand gestures.
Uses webcam and OpenCV for hand tracking.

Controls:
- Index finger extended: Draw
- Open hand (all fingers): Move cursor without drawing
- Closed fist for 2 seconds: Clear canvas
- Press ESC to exit

Requirements:
- opencv-python
- mediapipe
- numpy
"""

import cv2
import mediapipe as mp
import numpy as np
import time

# Initialize MediaPipe Hand detection
mp_hands = mp.solutions.hands
mp_drawing = mp.solutions.drawing_utils
hands = mp_hands.Hands(
    static_image_mode=False,
    max_num_hands=1,
    min_detection_confidence=0.5,
    min_tracking_confidence=0.5
)

# Initialize webcam
cap = cv2.VideoCapture(0)
# Get monitor resolution for fullscreen
screen_width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
screen_height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

# Create canvas
canvas = np.zeros((screen_height, screen_width, 3), dtype=np.uint8)

# Drawing parameters
drawing_color = (0, 255, 255)  # Yellow
brush_thickness = 5
prev_point = None

# State variables
is_drawing = False
clear_canvas_start_time = None
fist_detected = False

def detect_gesture(hand_landmarks):
    """
    Detect gesture based on hand landmarks.
    Returns: 
    - "draw" if index finger is extended
    - "move" if hand is open
    - "fist" if hand is closed in a fist
    - None if no valid gesture detected
    """
    if not hand_landmarks:
        return None
    
    # Get fingertip and knuckle positions
    fingertips = [hand_landmarks.landmark[mp_hands.HandLandmark.INDEX_FINGER_TIP],
                 hand_landmarks.landmark[mp_hands.HandLandmark.MIDDLE_FINGER_TIP],
                 hand_landmarks.landmark[mp_hands.HandLandmark.RING_FINGER_TIP],
                 hand_landmarks.landmark[mp_hands.HandLandmark.PINKY_TIP]]
    
    knuckles = [hand_landmarks.landmark[mp_hands.HandLandmark.INDEX_FINGER_PIP],
               hand_landmarks.landmark[mp_hands.HandLandmark.MIDDLE_FINGER_PIP],
               hand_landmarks.landmark[mp_hands.HandLandmark.RING_FINGER_PIP],
               hand_landmarks.landmark[mp_hands.HandLandmark.PINKY_PIP]]
    
    # Check if fingers are extended (fingertip y-coord < knuckle y-coord)
    extended_fingers = [fingertips[i].y < knuckles[i].y for i in range(4)]
    
    # Index finger for drawing
    if extended_fingers[0] and not any(extended_fingers[1:]):
        return "draw"
    # Open hand for moving
    elif all(extended_fingers):
        return "move"
    # Closed fist for clearing
    elif not any(extended_fingers):
        return "fist"
    
    return None

def main():
    global canvas, prev_point, is_drawing, clear_canvas_start_time, fist_detected
    
    # Create a named window and set to fullscreen
    window_name = "Gesture Canvas"
    cv2.namedWindow(window_name, cv2.WND_PROP_FULLSCREEN)
    cv2.setWindowProperty(window_name, cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)
    
    while cap.isOpened():
        ret, frame = cap.read()
        if not ret:
            break
            
        # Flip horizontally for a more natural interaction
        frame = cv2.flip(frame, 1)
        
        # Convert to RGB for MediaPipe
        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        results = hands.process(rgb_frame)
        
        # Create a copy of the canvas to display
        display_canvas = canvas.copy()
        
        # Get hand landmarks
        if results.multi_hand_landmarks:
            for hand_landmarks in results.multi_hand_landmarks:
                # Draw hand landmarks on the frame for debugging
                mp_drawing.draw_landmarks(frame, hand_landmarks, mp_hands.HAND_CONNECTIONS)
                
                # Get index finger position
                index_finger = hand_landmarks.landmark[mp_hands.HandLandmark.INDEX_FINGER_TIP]
                ix, iy = int(index_finger.x * frame.shape[1]), int(index_finger.y * frame.shape[0])
                
                # Draw cursor point on display canvas
                cv2.circle(display_canvas, (ix, iy), 10, (255, 255, 255), -1)
                
                # Detect gesture
                gesture = detect_gesture(hand_landmarks)
                
                if gesture == "draw":
                    is_drawing = True
                    if prev_point:
                        cv2.line(canvas, prev_point, (ix, iy), drawing_color, brush_thickness)
                    prev_point = (ix, iy)
                    
                elif gesture == "move":
                    is_drawing = False
                    prev_point = (ix, iy)
                    
                elif gesture == "fist":
                    is_drawing = False
                    if not fist_detected:
                        fist_detected = True
                        clear_canvas_start_time = time.time()
                    elif time.time() - clear_canvas_start_time > 2:  # 2 seconds of fist to clear
                        canvas = np.zeros((screen_height, screen_width, 3), dtype=np.uint8)
                        clear_canvas_start_time = None
                        fist_detected = False
                else:
                    is_drawing = False
                    fist_detected = False
        else:
            is_drawing = False
            prev_point = None
            fist_detected = False
        
        # Display text instructions
        instructions = "Draw: Index Finger | Move: Open Hand | Clear: Closed Fist (2s) | Exit: ESC"
        cv2.putText(display_canvas, instructions, (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 
                    0.7, (255, 255, 255), 2)
        
        # Display the resulting canvas
        cv2.imshow(window_name, display_canvas)
        
        # Exit when ESC is pressed
        if cv2.waitKey(5) & 0xFF == 27:
            break
    
    cap.release()
    cv2.destroyAllWindows()

if __name__ == "__main__":
    main()
