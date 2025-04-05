#!/usr/bin/env python
# Gesture Recognition Application using Kinect
# Detects and recognizes hand gestures using depth data

import numpy as np
import cv2
import sys
import time
from collections import deque
from pylibfreenect2 import Freenect2, SyncMultiFrameListener
from pylibfreenect2 import FrameType, Registration, Frame
from pylibfreenect2 import createConsoleLogger, setGlobalLogger
from pylibfreenect2 import LoggerLevel

# Reduce logging level to avoid too many messages
logger = createConsoleLogger(LoggerLevel.Warning)
setGlobalLogger(logger)

# Initialize Kinect device and choose pipeline
try:
    from pylibfreenect2 import OpenGLPacketPipeline
    pipeline = OpenGLPacketPipeline()
except:
    try:
        from pylibfreenect2 import OpenCLPacketPipeline
        pipeline = OpenCLPacketPipeline()
    except:
        from pylibfreenect2 import CpuPacketPipeline
        pipeline = CpuPacketPipeline()
print("Packet pipeline:", type(pipeline).__name__)

# Initialize Freenect2 device
fn = Freenect2()
num_devices = fn.enumerateDevices()
if num_devices == 0:
    print("No device connected!")
    sys.exit(1)

serial = fn.getDeviceSerialNumber(0)
device = fn.openDevice(serial, pipeline=pipeline)

# Setup frame listeners for both color and depth
types = FrameType.Color | FrameType.Ir | FrameType.Depth
listener = SyncMultiFrameListener(types)
device.setColorFrameListener(listener)
device.setIrAndDepthFrameListener(listener)

# Start device
device.start()

# Initialize registration
registration = Registration(device.getIrCameraParams(),
                          device.getColorCameraParams())

# Create frames for processing
undistorted = Frame(512, 424, 4)
registered = Frame(512, 424, 4)

# Parameters for hand detection
MIN_DEPTH = 500    # Minimum depth in mm
MAX_DEPTH = 800    # Maximum depth in mm
MIN_AREA = 1000    # Minimum contour area to be considered a hand
MAX_AREA = 15000   # Maximum contour area (to filter out large objects)

# Parameters for gesture recognition
GESTURE_HISTORY_SIZE = 20  # Number of frames to store for gesture detection
MOTION_THRESHOLD = 50      # Minimum pixel motion for gesture detection
SWIPE_THRESHOLD = 100      # Minimum pixel motion for swipe gestures
HAND_OPEN_THRESHOLD = 0.5  # Convexity ratio threshold for open hand

# Gesture history tracking
hand_positions = deque(maxlen=GESTURE_HISTORY_SIZE)
hand_areas = deque(maxlen=GESTURE_HISTORY_SIZE)
hand_convexity = deque(maxlen=GESTURE_HISTORY_SIZE)
current_gesture = "None"
gesture_confidence = 0
last_gesture_time = time.time()
gesture_cooldown = 1.0  # seconds between gestures

# Function to detect hand from depth image
def detect_hand(depth_data):
    # Filter by depth range to isolate hand
    mask = np.zeros_like(depth_data, dtype=np.uint8)
    mask[(depth_data > MIN_DEPTH) & (depth_data < MAX_DEPTH)] = 255
    
    # Apply morphological operations to remove noise
    kernel = np.ones((5, 5), np.uint8)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
    
    # Find contours in the thresholded image
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    
    # Find the largest contour which is likely to be the hand
    if contours:
        valid_contours = [c for c in contours if MIN_AREA < cv2.contourArea(c) < MAX_AREA]
        if valid_contours:
            largest_contour = max(valid_contours, key=cv2.contourArea)
            area = cv2.contourArea(largest_contour)
            
            # Get the contour's moments to find its center
            M = cv2.moments(largest_contour)
            if M["m00"] != 0:
                cx = int(M["m10"] / M["m00"])
                cy = int(M["m01"] / M["m00"])
                
                # Get convex hull and defects for hand shape analysis
                hull = cv2.convexHull(largest_contour, returnPoints=False)
                defects = None
                convexity_ratio = 0
                
                try:
                    defects = cv2.convexityDefects(largest_contour, hull)
                    if defects is not None:
                        # Calculate convexity ratio (area of contour / area of convex hull)
                        hull_points = cv2.convexHull(largest_contour, returnPoints=True)
                        hull_area = cv2.contourArea(hull_points)
                        if hull_area > 0:
                            convexity_ratio = area / hull_area
                except:
                    pass  # Sometimes convexityDefects fails
                
                # Draw contour and convex hull on mask for visualization
                vis_mask = cv2.cvtColor(mask, cv2.COLOR_GRAY2BGR)
                cv2.drawContours(vis_mask, [largest_contour], -1, (0, 255, 0), 2)
                
                # Draw convex hull
                if hull is not None:
                    hull_points = [largest_contour[h[0]] for h in hull]
                    cv2.polylines(vis_mask, [np.array(hull_points)], True, (255, 0, 0), 2)
                
                # Draw defects
                if defects is not None:
                    for i in range(defects.shape[0]):
                        s, e, f, d = defects[i, 0]
                        start = tuple(largest_contour[s][0])
                        end = tuple(largest_contour[e][0])
                        far = tuple(largest_contour[f][0])
                        
                        # Draw a circle at the farthest point
                        cv2.circle(vis_mask, far, 5, [0, 0, 255], -1)
                
                return (cx, cy), area, convexity_ratio, vis_mask
    
    return None, 0, 0, cv2.cvtColor(mask, cv2.COLOR_GRAY2BGR)

# Function to recognize gestures based on hand movement and shape
def recognize_gesture(positions, areas, convexity_ratios):
    global current_gesture, gesture_confidence, last_gesture_time
    
    # Need enough history for reliable detection
    if len(positions) < GESTURE_HISTORY_SIZE / 2:
        return "Waiting...", 0
    
    # Calculate movement
    start_pos = positions[0]
    end_pos = positions[-1]
    dx = end_pos[0] - start_pos[0]
    dy = end_pos[1] - start_pos[1]
    
    # Calculate area change
    area_change = areas[-1] / areas[0] if areas[0] > 0 else 1.0
    
    # Calculate average convexity ratio
    avg_convexity = sum(convexity_ratios) / len(convexity_ratios)
    
    # Check if enough time has passed since last gesture
    current_time = time.time()
    if current_time - last_gesture_time < gesture_cooldown:
        return current_gesture, gesture_confidence
    
    # Detect gestures
    new_gesture = "None"
    confidence = 0
    
    # Swipe gestures (significant horizontal movement)
    if abs(dx) > SWIPE_THRESHOLD and abs(dx) > abs(dy) * 2:
        # Check if movement is consistent (all points moving in same direction)
        is_consistent = True
        for i in range(1, len(positions)):
            if (positions[i][0] - positions[i-1][0]) * dx < 0:  # Direction changed
                is_consistent = False
                break
        
        if is_consistent:
            if dx > 0:
                new_gesture = "Swipe Right"
                confidence = min(1.0, abs(dx) / (SWIPE_THRESHOLD * 2))
            else:
                new_gesture = "Swipe Left"
                confidence = min(1.0, abs(dx) / (SWIPE_THRESHOLD * 2))
    
    # Swipe up/down (significant vertical movement)
    elif abs(dy) > SWIPE_THRESHOLD and abs(dy) > abs(dx) * 2:
        # Check if movement is consistent
        is_consistent = True
        for i in range(1, len(positions)):
            if (positions[i][1] - positions[i-1][1]) * dy < 0:  # Direction changed
                is_consistent = False
                break
        
        if is_consistent:
            if dy < 0:
                new_gesture = "Swipe Up"
                confidence = min(1.0, abs(dy) / (SWIPE_THRESHOLD * 2))
            else:
                new_gesture = "Swipe Down"
                confidence = min(1.0, abs(dy) / (SWIPE_THRESHOLD * 2))
    
    # Hand open/closed based on convexity ratio
    elif abs(dx) < MOTION_THRESHOLD and abs(dy) < MOTION_THRESHOLD:
        if avg_convexity > HAND_OPEN_THRESHOLD:
            new_gesture = "Hand Open"
            confidence = min(1.0, (avg_convexity - HAND_OPEN_THRESHOLD) * 3)
        else:
            new_gesture = "Hand Closed"
            confidence = min(1.0, (HAND_OPEN_THRESHOLD - avg_convexity) * 3)
        
    # "Push" gesture - hand area growing significantly
    elif area_change > 1.5 and abs(dx) < MOTION_THRESHOLD and abs(dy) < MOTION_THRESHOLD:
        new_gesture = "Push"
        confidence = min(1.0, (area_change - 1.5) * 2)
    
    # "Pull" gesture - hand area shrinking significantly
    elif area_change < 0.7 and abs(dx) < MOTION_THRESHOLD and abs(dy) < MOTION_THRESHOLD:
        new_gesture = "Pull"
        confidence = min(1.0, (0.7 - area_change) * 3)
    
    # Update gesture only if confidence is high enough
    if confidence > 0.7 and new_gesture != "None":
        current_gesture = new_gesture
        gesture_confidence = confidence
        last_gesture_time = current_time
    
    return current_gesture, gesture_confidence

# Create windows
cv2.namedWindow("Depth", cv2.WINDOW_NORMAL)
cv2.namedWindow("Hand Detection", cv2.WINDOW_NORMAL)
cv2.namedWindow("Gesture Recognition", cv2.WINDOW_NORMAL)

# Create a blank canvas for visualization
gesture_canvas = np.zeros((400, 600, 3), dtype=np.uint8)

# Display instructions
def draw_instructions():
    instructions = np.zeros((400, 600, 3), dtype=np.uint8)
    cv2.putText(instructions, "Gesture Recognition", (20, 40), cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
    cv2.putText(instructions, "Available Gestures:", (20, 100), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (200, 200, 200), 1)
    cv2.putText(instructions, "- Swipe Left/Right/Up/Down", (30, 140), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (200, 200, 200), 1)
    cv2.putText(instructions, "- Hand Open/Closed", (30, 170), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (200, 200, 200), 1)
    cv2.putText(instructions, "- Push/Pull", (30, 200), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (200, 200, 200), 1)
    cv2.putText(instructions, "Controls:", (20, 240), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (200, 200, 200), 1)
    cv2.putText(instructions, "- Press 'q' to quit", (30, 280), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (200, 200, 200), 1)
    cv2.putText(instructions, "- Press 'r' to reset gesture history", (30, 310), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (200, 200, 200), 1)
    cv2.putText(instructions, "- Press '+/-' to adjust detection depth", (30, 340), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (200, 200, 200), 1)
    
    return instructions

instructions = draw_instructions()
cv2.imshow("Gesture Recognition", instructions)

print("\nGesture Recognition Application")
print("-------------------------------")
print("Place your hand in front of the Kinect to detect gestures")
print("Controls:")
print("  - Press 'q' to quit")
print("  - Press 'r' to reset gesture history")
print("  - Press '+' or '-' to adjust detection depth")

# Main loop
try:
    while True:
        # Wait for new frames
        frames = listener.waitForNewFrame()
        color = frames["color"]
        depth = frames["depth"]
        
        # Get images as numpy arrays
        depth_data = depth.asarray()
        color_data = color.asarray()
        
        # Undistort and register
        registration.apply(color, depth, undistorted, registered)
        registered_data = registered.asarray(np.uint8)
        
        # Normalize depth for visualization
        depth_vis = cv2.normalize(depth_data, None, 0, 255, cv2.NORM_MINMAX, dtype=cv2.CV_8U)
        depth_vis = cv2.applyColorMap(depth_vis, cv2.COLORMAP_JET)
        
        # Detect hand
        hand_position, hand_area, convexity_ratio, hand_vis = detect_hand(depth_data.copy())
        
        # If hand detected, update history and recognize gesture
        if hand_position:
            # Add to history
            hand_positions.append(hand_position)
            hand_areas.append(hand_area)
            hand_convexity.append(convexity_ratio)
            
            # Recognize gesture
            gesture, confidence = recognize_gesture(list(hand_positions), list(hand_areas), list(hand_convexity))
            
            # Draw hand position trail
            if len(hand_positions) > 1:
                gesture_canvas = np.zeros((400, 600, 3), dtype=np.uint8)
                
                # Draw gesture name
                cv2.putText(gesture_canvas, f"Gesture: {gesture}", (20, 40), 
                           cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
                cv2.putText(gesture_canvas, f"Confidence: {confidence:.2f}", (20, 80), 
                           cv2.FONT_HERSHEY_SIMPLEX, 0.7, (200, 200, 200), 1)
                
                # Draw trail of hand positions
                for i in range(1, len(hand_positions)):
                    start_x = int(hand_positions[i-1][0] * 600 / 512)
                    start_y = int(hand_positions[i-1][1] * 400 / 424)
                    end_x = int(hand_positions[i][0] * 600 / 512)
                    end_y = int(hand_positions[i][1] * 400 / 424)
                    
                    # Color gradient from blue to red based on position in history
                    color = (
                        int(255 * i / len(hand_positions)),  # B
                        0,  # G
                        int(255 * (1 - i / len(hand_positions)))  # R
                    )
                    
                    cv2.line(gesture_canvas, (start_x, start_y), (end_x, end_y), color, 2)
                    
                # Draw current hand position
                cv2.circle(gesture_canvas, 
                           (int(hand_positions[-1][0] * 600 / 512), 
                            int(hand_positions[-1][1] * 400 / 424)), 
                           10, (0, 255, 0), -1)
                
                # Draw visual cue for the detected gesture
                if gesture == "Swipe Left":
                    cv2.arrowedLine(gesture_canvas, (400, 200), (200, 200), (0, 255, 255), 3)
                elif gesture == "Swipe Right":
                    cv2.arrowedLine(gesture_canvas, (200, 200), (400, 200), (0, 255, 255), 3)
                elif gesture == "Swipe Up":
                    cv2.arrowedLine(gesture_canvas, (300, 300), (300, 100), (0, 255, 255), 3)
                elif gesture == "Swipe Down":
                    cv2.arrowedLine(gesture_canvas, (300, 100), (300, 300), (0, 255, 255), 3)
                elif gesture == "Hand Open":
                    cv2.circle(gesture_canvas, (300, 200), 50, (0, 255, 255), 3)
                elif gesture == "Hand Closed":
                    cv2.circle(gesture_canvas, (300, 200), 20, (0, 255, 255), -1)
                elif gesture == "Push":
                    cv2.circle(gesture_canvas, (300, 200), 30, (0, 255, 255), 3)
                    cv2.circle(gesture_canvas, (300, 200), 50, (0, 255, 255), 1)
                    cv2.circle(gesture_canvas, (300, 200), 70, (0, 255, 255), 1)
                elif gesture == "Pull":
                    cv2.circle(gesture_canvas, (300, 200), 70, (0, 255, 255), 3)
                    cv2.circle(gesture_canvas, (300, 200), 50, (0, 255, 255), 1)
                    cv2.circle(gesture_canvas, (300, 200), 30, (0, 255, 255), 1)
                
                # Display depth thresholds
                cv2.putText(gesture_canvas, f"Depth range: {MIN_DEPTH}-{MAX_DEPTH} mm", 
                           (20, 360), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (150, 150, 150), 1)
            
            # Show gesture canvas
            cv2.imshow("Gesture Recognition", gesture_canvas)
        
        # Show images
        cv2.imshow("Depth", depth_vis)
        cv2.imshow("Hand Detection", hand_vis)
        
        # Process keyboard input
        key = cv2.waitKey(1)
        
        # Reset gesture history
        if key == ord('r'):
            hand_positions.clear()
            hand_areas.clear()
            hand_convexity.clear()
            current_gesture = "None"
            gesture_confidence = 0
            cv2.imshow("Gesture Recognition", instructions)
        
        # Adjust detection depth
        elif key == ord('+') or key == ord('='):
            MAX_DEPTH = min(MAX_DEPTH + 50, 4000)
            print(f"Depth range: {MIN_DEPTH}-{MAX_DEPTH} mm")
        elif key == ord('-') or key == ord('_'):
            MAX_DEPTH = max(MAX_DEPTH - 50, MIN_DEPTH + 100)
            print(f"Depth range: {MIN_DEPTH}-{MAX_DEPTH} mm")
        
        # Quit
        elif key == ord('q') or key == 27:  # 'q' or ESC
            break
        
        # Release frames
        listener.release(frames)

except KeyboardInterrupt:
    print("\nInterrupted by user")
except Exception as e:
    print(f"\nError: {e}")
finally:
    # Stop and close device
    device.stop()
    device.close()
    
    # Close all open windows
    cv2.destroyAllWindows()
    
    print("Gesture recognition application closed")
