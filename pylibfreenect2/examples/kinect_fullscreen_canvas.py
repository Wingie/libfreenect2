#!/usr/bin/env python
# Kinect Full-Screen Drawing Canvas
# This script creates a full-screen drawing application controlled by hand gestures
# detected by the Kinect sensor

import numpy as np
import cv2
import sys
from pylibfreenect2 import Freenect2, SyncMultiFrameListener
from pylibfreenect2 import FrameType, Registration, Frame
from pylibfreenect2 import createConsoleLogger, setGlobalLogger
from pylibfreenect2 import LoggerLevel

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

# Reduce logging level to avoid too many messages
logger = createConsoleLogger(LoggerLevel.Warning)
setGlobalLogger(logger)

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

# Get screen resolution
screen = cv2.VideoCapture(0)
screen_width = int(screen.get(cv2.CAP_PROP_FRAME_WIDTH))
screen_height = int(screen.get(cv2.CAP_PROP_FRAME_HEIGHT))
screen.release()

# Create a full-screen canvas
canvas = np.zeros((screen_height, screen_width, 3), dtype=np.uint8)

# Parameters for hand tracking
MIN_DEPTH = 500    # Minimum depth in mm
MAX_DEPTH = 800    # Maximum depth in mm
MIN_AREA = 50      # Minimum contour area to be considered a hand
SMOOTHING = 0.3    # Movement smoothing factor (0-1)

# Drawing parameters
prev_x, prev_y = None, None
drawing = False
brush_size = 5
brush_color = (0, 255, 255)  # Yellow color (BGR)

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
        largest_contour = max(contours, key=cv2.contourArea)
        if cv2.contourArea(largest_contour) > MIN_AREA:
            # Get the contour's moments to find its center
            M = cv2.moments(largest_contour)
            if M["m00"] != 0:
                cx = int(M["m10"] / M["m00"])
                cy = int(M["m01"] / M["m00"])
                
                # Calculate the tip of the hand (assuming it's the highest point)
                hand_tip = tuple(largest_contour[largest_contour[:, :, 1].argmin()][0])
                
                return hand_tip, mask
    
    return None, mask

# Create a fullscreen window
window_name = "Kinect Full-Screen Canvas"
cv2.namedWindow(window_name, cv2.WND_PROP_FULLSCREEN)
cv2.setWindowProperty(window_name, cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)

print("Kinect Full-Screen Drawing Canvas")
print("--------------------------------")
print("Controls:")
print("  - Move your hand in front of the Kinect to control the cursor")
print("  - Move your hand closer to the Kinect to start drawing")
print("  - Move your hand away from the Kinect to stop drawing")
print("  - Press 'c' to clear the canvas")
print("  - Press 'r' for red, 'g' for green, 'b' for blue, 'y' for yellow")
print("  - Press '+' or '-' to change brush size")
print("  - Press 'q' or ESC to quit")

# Main loop
try:
    while True:
        # Wait for new frames
        frames = listener.waitForNewFrame()
        depth = frames["depth"]
        
        # Get depth data as numpy array
        depth_data = depth.asarray()
        
        # Detect hand
        hand_position, hand_mask = detect_hand(depth_data.copy())
        
        # Create a copy of the canvas for display
        display_img = canvas.copy()
        
        # Handle hand detection and drawing
        if hand_position:
            # Flip the x coordinate for mirroring
            hand_x = 512 - hand_position[0]
            hand_y = hand_position[1]
            
            # Scale hand position to screen resolution
            screen_x = int(hand_x * screen_width / 512)
            screen_y = int(hand_y * screen_height / 424)
            
            # Calculate depth value at hand position
            depth_at_hand = depth_data[hand_position[1], hand_position[0]]
            
            # Determine if we're in drawing mode based on depth
            current_drawing = (depth_at_hand < MIN_DEPTH + 100)
            
            # Draw cursor on display (different color based on drawing mode)
            cv2.circle(display_img, (screen_x, screen_y), 10, 
                      (0, 0, 255) if current_drawing else (0, 255, 0), -1)
            
            # Smooth hand movement
            if prev_x is not None and prev_y is not None:
                smoothed_x = int(prev_x * SMOOTHING + screen_x * (1 - SMOOTHING))
                smoothed_y = int(prev_y * SMOOTHING + screen_y * (1 - SMOOTHING))
                
                # Draw on canvas if in drawing mode
                if current_drawing:
                    cv2.line(canvas, (prev_x, prev_y), (smoothed_x, smoothed_y), 
                            brush_color, brush_size)
                
                prev_x, prev_y = smoothed_x, smoothed_y
            else:
                prev_x, prev_y = screen_x, screen_y
            
            # Display drawing mode status
            cv2.putText(display_img, "Drawing: {}".format("ON" if current_drawing else "OFF"), 
                       (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 1, 
                       (0, 0, 255) if current_drawing else (0, 255, 0), 2)
            
            # Display brush info
            cv2.putText(display_img, "Brush size: {}".format(brush_size), 
                       (10, 70), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
            
            # Show a color sample
            cv2.circle(display_img, (50, 100), brush_size * 2, brush_color, -1)
        
        # Show full-screen canvas
        cv2.imshow(window_name, display_img)
        
        # Process keyboard input
        key = cv2.waitKey(1)
        
        # Clear canvas
        if key == ord('c'):
            canvas = np.zeros((screen_height, screen_width, 3), dtype=np.uint8)
        
        # Color selection
        elif key == ord('r'):
            brush_color = (0, 0, 255)  # Red (BGR)
        elif key == ord('g'):
            brush_color = (0, 255, 0)  # Green (BGR)
        elif key == ord('b'):
            brush_color = (255, 0, 0)  # Blue (BGR)
        elif key == ord('y'):
            brush_color = (0, 255, 255)  # Yellow (BGR)
        
        # Brush size adjustment
        elif key == ord('+') or key == ord('='):
            brush_size = min(brush_size + 1, 20)
        elif key == ord('-') or key == ord('_'):
            brush_size = max(brush_size - 1, 1)
        
        # Adjust depth range
        elif key == ord('['):
            MIN_DEPTH = max(MIN_DEPTH - 50, 100)
            print(f"Depth range: {MIN_DEPTH}-{MAX_DEPTH} mm")
        elif key == ord(']'):
            MIN_DEPTH = min(MIN_DEPTH + 50, MAX_DEPTH - 100)
            print(f"Depth range: {MIN_DEPTH}-{MAX_DEPTH} mm")
        elif key == ord('{'):
            MAX_DEPTH = max(MAX_DEPTH - 50, MIN_DEPTH + 100)
            print(f"Depth range: {MIN_DEPTH}-{MAX_DEPTH} mm")
        elif key == ord('}'):
            MAX_DEPTH = min(MAX_DEPTH + 50, 4000)
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
    
    # Save canvas as image file
    cv2.imwrite("kinect_drawing.png", canvas)
    print("Drawing saved as 'kinect_drawing.png'")
