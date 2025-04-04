#!/usr/bin/env python
# Real-time Kinect Point Cloud Viewer
# This script continuously updates the point cloud visualization in matplotlib

import numpy as np
import cv2
import sys
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d import Axes3D
from pylibfreenect2 import Freenect2, SyncMultiFrameListener
from pylibfreenect2 import FrameType, Registration, Frame
import time

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
device = fn.openDevice(serial, pipeline=pipeline) # <<< Make sure this line is present and correct

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
point_step = 15     # Take every Nth point to reduce density
display_step = 10   # Further downsample for display

# Get the depth camera intrinsic parameters
depth_params = device.getIrCameraParams() # <<< Ensure 'device' is defined before this line
fx = depth_params.fx
fy = depth_params.fy
cx = depth_params.cx
cy = depth_params.cy

print(f"Depth camera parameters: fx={fx}, fy={fy}, cx={cx}, cy={cy}")

# Setup matplotlib for interactive plotting
plt.ion()  # Enable interactive mode
fig = plt.figure(figsize=(10, 8))
ax = fig.add_subplot(111, projection='3d')

# Initial empty plot
scatter = None
rotation_angle = 0

print("Starting real-time point cloud visualization...")
print("Controls:")
print("  - Close the matplotlib window to exit")
print("  - Press Ctrl+C in the terminal to stop")

try:
    # Main loop
    while True:
        start_time = time.time()

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

        # Create arrays for point cloud data
        points = []
        colors = []

        # Process every Nth point to improve performance
        for y in range(0, 424, point_step):
            for x in range(0, 512, point_step):
                depth_value = depth_data[y, x]
                if min_depth < depth_value < max_depth:
                    # Convert depth to 3D point
                    Z = depth_value  # In mm
                    X = (x - cx) * Z / fx
                    Y = (y - cy) * Z / fy

                    # Get color for this point (BGR to RGB)
                    b = registered_data[y, x, 0] / 255.0
                    g = registered_data[y, x, 1] / 255.0
                    r = registered_data[y, x, 2] / 255.0

                    # Add to point cloud
                    points.append([X, Y, Z])
                    colors.append([r, g, b])

        # Release frames
        listener.release(frames)

        # Convert to numpy arrays
        if len(points) > 0:
            points = np.array(points)
            colors = np.array(colors)

            # Downsample further for matplotlib (it's slow with too many points)
            if len(points) > display_step:
                display_indices = np.arange(0, len(points), display_step)
                display_points = points[display_indices]
                display_colors = colors[display_indices]
            else:
                display_points = points
                display_colors = colors

            # Clear previous plot
            ax.clear()

            # Extract X, Y, Z coordinates
            xs = display_points[:, 0]
            ys = display_points[:, 1]
            zs = display_points[:, 2]

            # --- MODIFIED LINE ---
            # Plot points as squares
            # 's' specifies a square marker
            # 's' argument controls the size (area in points^2), adjust as needed
            ax.scatter(xs, ys, zs, c=display_colors, marker='s', s=10)
            # --- END MODIFIED LINE ---

            # Set labels and title
            ax.set_xlabel('X (mm)')
            ax.set_ylabel('Y (mm)')
            ax.set_zlabel('Z (mm)')
            ax.set_title(f'Kinect Point Cloud - {len(display_points)} points (Square Markers)')

            # Auto-adjust the view boundaries
            try:
                max_range = np.array([
                    xs.max()-xs.min(),
                    ys.max()-ys.min(),
                    zs.max()-zs.min()
                ]).max() / 2.0

                mid_x = (xs.max()+xs.min()) * 0.5
                mid_y = (ys.max()+ys.min()) * 0.5
                mid_z = (zs.max()+zs.min()) * 0.5

                ax.set_xlim(mid_x - max_range, mid_x + max_range)
                ax.set_ylim(mid_y - max_range, mid_y + max_range)
                ax.set_zlim(mid_z - max_range, mid_z + max_range)
            except ValueError:
                # Handle case where min/max might fail (e.g., only one point)
                pass

            # Rotate view for each frame
            rotation_angle = (rotation_angle + 1) % 360
            ax.view_init(elev=30, azim=rotation_angle)

            # Draw and wait a bit
            plt.draw()
            plt.pause(0.001)  # Short pause to allow GUI events to process
        else:
            # No need to print this every frame if nothing is seen
            # print("No valid points found in the current frame.")
            pass # Just skip plotting if no points

        # Calculate and print frame rate
        elapsed = time.time() - start_time
        # Avoid division by zero if elapsed time is too small
        fps = (1/elapsed) if elapsed > 0 else 0
        print(f"\rFrame time: {elapsed:.3f}s ({fps:.1f} FPS)", end="")

        # Check if figure is still open
        if not plt.fignum_exists(fig.number):
            print("\nMatplotlib window closed. Exiting...")
            break

except KeyboardInterrupt:
    print("\nInterrupted by user. Closing...")
except Exception as e:
    print(f"\nError: {e}")
finally:
    # Stop and close device
    # Add check if device was successfully opened
    if 'device' in locals() and device:
        device.stop()
        device.close()

    # Close all matplotlib windows
    plt.close('all')

    print("\nPoint cloud viewer closed")