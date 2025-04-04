#!/usr/bin/env python
# Touchless Drawing Canvas with Kinect
# This script allows users to draw in the air using hand movements
# Detected by the Kinect sensor

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

# Canvas to draw on
canvas = np.zeros((600, 800, 3), dtype=np.uint8)

# Parameters for hand tracking
# The values can be adjusted based on the environment
MIN_DEPTH = 500    # Minimum depth in mm
MAX_DEPTH = 800    # Maximum depth in mm
MIN_AREA = 50      # Minimum contour area to be considered a hand
SMOOTHING = 0.3    # Movement smoothing factor (0-1)

# Tracking variables
prev_x, prev_y = None, None
draw_mode = False
brush_size = 5
brush_color = (0, 255, 255)  # Yellow color (BGR)
eraser_mode = False

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
                # You can modify this logic to detect fingertips more accurately
                hand_tip = tuple(largest_contour[largest_contour[:, :, 1].argmin()][0])
                return hand_tip, mask
    
    return None, mask

print("Touchless Drawing Canvas")
print("------------------------")
print("Controls:")
print("  - Move your hand in front of the Kinect to draw")
print("  - Extend your hand forward (closer to Kinect) to start drawing")
print("  - Pull your hand back to stop drawing")
print("  - Press 'c' to clear the canvas")
print("  - Press 'r' for red, 'g' for green, 'b' for blue, 'y' for yellow")
print("  - Press '+' or '-' to change brush size")
print("  - Press 'e' to toggle eraser mode")
print("  - Press 'q' or ESC to quit")

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
        
        # Detect hand
        hand_position, hand_mask = detect_hand(depth_data.copy())
        
        # Create a mirrored display image
        display_img = cv2.flip(registered_data, 1)
        
        # Draw visualization
        if hand_position:
            # Flip the x coordinate for mirroring
            hand_x = 512 - hand_position[0]  # Flip x for mirroring
            hand_y = hand_position[1]
            
            # Scale hand position to canvas size
            canvas_x = int(hand_x * canvas.shape[1] / 512)
            canvas_y = int(hand_y * canvas.shape[0] / 424)
            
            # Calculate depth value at hand position
            depth_at_hand = depth_data[hand_position[1], hand_position[0]]
            
            # Draw mode depends on depth
            current_draw_mode = (depth_at_hand < MIN_DEPTH + 100)
            
            # Draw a circle at the hand position for visual feedback
            cv2.circle(display_img, (hand_x, hand_y), 10, (0, 0, 255) if current_draw_mode else (0, 255, 0), -1)
            
            # Smooth hand movement
            if prev_x is not None and prev_y is not None:
                smoothed_x = int(prev_x * SMOOTHING + canvas_x * (1 - SMOOTHING))
                smoothed_y = int(prev_y * SMOOTHING + canvas_y * (1 - SMOOTHING))
                
                # Draw on canvas if in draw mode
                if current_draw_mode:
                    if eraser_mode:
                        cv2.circle(canvas, (smoothed_x, smoothed_y), brush_size * 2, (0, 0, 0), -1)
                    else:
                        cv2.line(canvas, (prev_x, prev_y), (smoothed_x, smoothed_y), brush_color, brush_size)
                
                prev_x, prev_y = smoothed_x, smoothed_y
            else:
                prev_x, prev_y = canvas_x, canvas_y
            
            # Display draw mode status
            cv2.putText(display_img, "Drawing: {}".format("ON" if current_draw_mode else "OFF"), 
                        (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255) if current_draw_mode else (0, 255, 0), 2)
        
        # Show images
        cv2.imshow("Registered", display_img)
        cv2.imshow("Hand Mask", hand_mask)
        cv2.imshow("Canvas", canvas)
        
        # Process keyboard input
        key = cv2.waitKey(1)
        
        # Clear canvas
        if key == ord('c'):
            canvas = np.zeros((600, 800, 3), dtype=np.uint8)
        
        # Color selection
        elif key == ord('r'):
            brush_color = (0, 0, 255)  # Red (BGR)
            eraser_mode = False
        elif key == ord('g'):
            brush_color = (0, 255, 0)  # Green (BGR)
            eraser_mode = False
        elif key == ord('b'):
            brush_color = (255, 0, 0)  # Blue (BGR)
            eraser_mode = False
        elif key == ord('y'):
            brush_color = (0, 255, 255)  # Yellow (BGR)
            eraser_mode = False
        
        # Brush size adjustment
        elif key == ord('+') or key == ord('='):
            brush_size = min(brush_size + 1, 20)
        elif key == ord('-') or key == ord('_'):
            brush_size = max(brush_size - 1, 1)
            
        # Toggle eraser mode
        elif key == ord('e'):
            eraser_mode = not eraser_mode
            
        # Quit
        elif key == ord('q') or key == 27:  # 'q' or ESC
            break
        
        # Release frames
        listener.release(frames)

except KeyboardInterrupt:
    pass

finally:
    # Stop and close device
    device.stop()
    device.close()
    
    # Close all open windows
    cv2.destroyAllWindows()

    # Save canvas as image file
    cv2.imwrite("touchless_drawing.png", canvas)
    print("Drawing saved as 'touchless_drawing.png'")