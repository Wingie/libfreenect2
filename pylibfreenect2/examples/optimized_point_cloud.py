#!/usr/bin/env python
# Optimized Real-time Kinect Point Cloud Viewer
# This script improves on point_cloud.py with better performance

import numpy as np
import cv2
import sys
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d import Axes3D
from pylibfreenect2 import Freenect2, SyncMultiFrameListener
from pylibfreenect2 import FrameType, Registration, Frame
from pylibfreenect2 import createConsoleLogger, setGlobalLogger
from pylibfreenect2 import LoggerLevel
import time

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

# Point cloud parameters
max_depth = 4500    # Maximum depth in mm
min_depth = 500     # Minimum depth in mm
point_step = 20     # Take every Nth point to reduce density (increased from 15)
display_step = 1    # No additional downsampling for display since we already downsample

# Get the depth camera intrinsic parameters
depth_params = device.getIrCameraParams()
fx = depth_params.fx
fy = depth_params.fy
cx = depth_params.cx
cy = depth_params.cy

print(f"Depth camera parameters: fx={fx}, fy={fy}, cx={cx}, cy={cy}")

# Setup matplotlib for interactive plotting
plt.ion()  # Enable interactive mode
fig = plt.figure(figsize=(10, 8))
ax = fig.add_subplot(111, projection='3d')

# Set fixed view limits to avoid recalculation on each frame
ax.set_xlim(-2000, 2000)
ax.set_ylim(-2000, 2000)
ax.set_zlim(0, 4500)

# Set labels and title
ax.set_xlabel('X (mm)')
ax.set_ylabel('Y (mm)')
ax.set_zlabel('Z (mm)')
ax.set_title('Kinect Point Cloud')

# Initial empty plot
scatter = None
rotation_angle = 0
frame_count = 0

# Color mapping mode
color_mode = "rgb"  # Options: "rgb", "depth", "height", "distance"

print("Starting optimized real-time point cloud visualization...")
print("Controls:")
print("  - Close the matplotlib window to exit")
print("  - Press Ctrl+C in the terminal to stop")
print("  - Press '1' for RGB color mode")
print("  - Press '2' for depth-based color mode")
print("  - Press '3' for height-based color mode")
print("  - Press '4' for distance-based color mode")

try:
    # Main loop
    while True:
        start_time = time.time()
        frame_count += 1

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

        # OPTIMIZATION: Use numpy grid operations instead of loops
        # Create coordinate grids (sampling every point_step pixels)
        y_indices, x_indices = np.mgrid[0:424:point_step, 0:512:point_step]
        y_indices = y_indices.flatten()
        x_indices = x_indices.flatten()
        
        # Get depth values for all points
        depth_values = depth_data[y_indices, x_indices]
        
        # Filter by depth range
        valid_points = (depth_values > min_depth) & (depth_values < max_depth)
        
        if np.any(valid_points):
            # Extract valid coordinates
            valid_y = y_indices[valid_points]
            valid_x = x_indices[valid_points]
            valid_depths = depth_values[valid_points]
            
            # Calculate 3D coordinates
            Z = valid_depths
            X = (valid_x - cx) * Z / fx
            Y = (valid_y - cy) * Z / fy
            
            # Get colors for valid points
            if color_mode == "rgb":
                # RGB color from registered image
                colors = registered_data[valid_y, valid_x, :3].astype(float) / 255.0
                # Convert BGR to RGB
                colors = colors[:, [2, 1, 0]]
            elif color_mode == "depth":
                # Color based on depth (red=near, blue=far)
                norm_depths = (valid_depths - min_depth) / (max_depth - min_depth)
                colors = np.zeros((len(valid_depths), 3))
                colors[:, 0] = 1 - norm_depths  # Red channel (inverse of depth)
                colors[:, 2] = norm_depths      # Blue channel
            elif color_mode == "height":
                # Color based on height (Y coordinate)
                min_y, max_y = -1000, 1000  # Approximate height range
                norm_heights = np.clip((Y - min_y) / (max_y - min_y), 0, 1)
                colors = plt.cm.viridis(norm_heights)[:, :3]  # Use viridis colormap
            elif color_mode == "distance":
                # Color based on distance from origin (in XZ plane)
                distances = np.sqrt(X**2 + Z**2)
                max_dist = 3000  # Maximum expected distance
                norm_distances = np.clip(distances / max_dist, 0, 1)
                colors = plt.cm.plasma(norm_distances)[:, :3]  # Use plasma colormap
            
            # Release frames
            listener.release(frames)
            
            # OPTIMIZATION: Update scatter plot instead of recreating it
            if scatter is None:
                scatter = ax.scatter(X, Y, Z, c=colors, s=2)
                fig.canvas.draw()
            else:
                scatter._offsets3d = (X, Y, Z)
                scatter.set_color(colors)
            
            # Update title with point count
            ax.set_title(f'Kinect Point Cloud - {len(X)} points')
            
            # OPTIMIZATION: Rotate view less frequently
            if frame_count % 3 == 0:  # Only rotate every 3 frames
                rotation_angle = (rotation_angle + 1) % 360
                ax.view_init(elev=30, azim=rotation_angle)
            
            # Draw with minimal update
            fig.canvas.draw_idle()
            plt.pause(0.001)  # Short pause to allow GUI events to process
            
            # Calculate and print frame rate
            elapsed = time.time() - start_time
            print(f"\rFrame time: {elapsed:.3f}s ({1/elapsed:.1f} FPS) - Mode: {color_mode}", end="")
            
            # Check if figure is still open
            if not plt.fignum_exists(fig.number):
                print("\nMatplotlib window closed. Exiting...")
                break
            
            # Check for key presses (using cv2 for keyboard input)
            key = cv2.waitKey(1) & 0xFF
            if key == ord('1'):
                color_mode = "rgb"
            elif key == ord('2'):
                color_mode = "depth"
            elif key == ord('3'):
                color_mode = "height"
            elif key == ord('4'):
                color_mode = "distance"
        else:
            listener.release(frames)
            print("No valid points found in the current frame.")

except KeyboardInterrupt:
    print("\nInterrupted by user. Closing...")
except Exception as e:
    print(f"\nError: {e}")
finally:
    # Stop and close device
    device.stop()
    device.close()

    # Close all matplotlib windows
    plt.close('all')

    print("Point cloud viewer closed")
