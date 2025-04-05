#!/usr/bin/env python
# Artistic Kinect Point Cloud Visualizer using OpenCV
# This is a simpler version that avoids GUI threading issues on macOS

import numpy as np
import cv2
import sys
import time
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

# Point cloud parameters
max_depth = 4500    # Maximum depth in mm
min_depth = 500     # Minimum depth in mm
point_step = 4      # Take every Nth point

# Get the depth camera intrinsic parameters
depth_params = device.getIrCameraParams()
fx = depth_params.fx
fy = depth_params.fy
cx = depth_params.cx
cy = depth_params.cy

print(f"Depth camera parameters: fx={fx}, fy={fy}, cx={cx}, cy={cy}")

# Visualization parameters
art_mode = "rgb"        # Initial mode
point_size = 2          # Point size for rendered points
canvas_width = 1280     # Visualization window width
canvas_height = 720     # Visualization window height
view_angle = 0          # Initial view angle
rotation_speed = 1      # Rotation speed
auto_rotate = True      # Auto-rotation enabled
paused = False          # Paused state for auto-rotation
top_view = False        # Top-down view
color_shift = 0         # Color cycling parameter
particle_effect = False # Particle effect
temporal_blend = 0.0    # Blending with previous frame (motion trail)
previous_frame = None   # Previous frame for temporal blending
flip_x = False          # Flip X axis (left-right mirror)
flip_z = False          # Flip Z axis (front-back)
flip_y = True           # Flip Y axis (up-down) - enabled by default for correct orientation
view_elevation = 30     # Elevation angle for 3D view

# Create windows
cv2.namedWindow("Artistic Point Cloud", cv2.WINDOW_NORMAL)
cv2.resizeWindow("Artistic Point Cloud", canvas_width, canvas_height)

# Define color palettes using color lookup tables (LUTs)
def create_rainbow_lut():
    lut = np.zeros((256, 1, 3), dtype=np.uint8)
    for i in range(256):
        hue = int(i * 180.0 / 256)
        hsv = np.array([[[hue, 255, 255]]], dtype=np.uint8)
        rgb = cv2.cvtColor(hsv, cv2.COLOR_HSV2BGR)
        lut[i] = rgb
    return lut

def create_cyberpunk_lut():
    lut = np.zeros((256, 1, 3), dtype=np.uint8)
    for i in range(256):
        # Cyberpunk colors: purple to cyan to pink
        if i < 85:
            # Purple to cyan gradient
            r = int(255 * (1 - i / 85.0))
            g = int(127 * (i / 85.0))
            b = 255
        elif i < 170:
            # Cyan to pink gradient
            j = i - 85
            r = int(255 * (j / 85.0))
            g = 127 + int(128 * (1 - j / 85.0))
            b = 255
        else:
            # Pink to purple gradient
            j = i - 170
            r = 255
            g = int(127 * (1 - j / 85.0))
            b = 255
        lut[i] = [b, g, r]  # OpenCV uses BGR
    return lut

def create_thermal_lut():
    lut = np.zeros((256, 1, 3), dtype=np.uint8)
    for i in range(256):
        # Black to blue to red to yellow
        if i < 64:
            # Black to blue
            r, g = 0, 0
            b = int(255 * (i / 64.0))
        elif i < 128:
            # Blue to purple
            j = i - 64
            r = int(255 * (j / 64.0))
            g = 0
            b = 255
        elif i < 192:
            # Purple to red
            j = i - 128
            r = 255
            g = 0
            b = int(255 * (1 - j / 64.0))
        else:
            # Red to yellow
            j = i - 192
            r = 255
            g = int(255 * (j / 64.0))
            b = 0
        lut[i] = [b, g, r]  # OpenCV uses BGR
    return lut

def create_matrix_lut():
    lut = np.zeros((256, 1, 3), dtype=np.uint8)
    for i in range(256):
        # Green matrix-style gradient
        r = 0
        g = int(i)
        b = 0
        lut[i] = [b, g, r]  # OpenCV uses BGR
    return lut

def create_neon_lut():
    lut = np.zeros((256, 1, 3), dtype=np.uint8)
    for i in range(256):
        # Neon glow effect with black background
        val = i
        if val < 100:
            # Dark areas are black
            r, g, b = 0, 0, 0
        else:
            # Bright areas get neon colors
            # Use sine waves with different phases for color oscillation
            phase = (i / 255.0) * 6.28  # 0 to 2π
            r = int(200 * np.sin(phase) ** 2) + 55
            g = int(200 * np.sin(phase + 2.09) ** 2) + 55  # Phase shift by ~2π/3
            b = int(200 * np.sin(phase + 4.18) ** 2) + 55  # Phase shift by ~4π/3
        lut[i] = [b, g, r]  # OpenCV uses BGR
    return lut

# Create color LUTs
color_luts = {
    "rainbow": create_rainbow_lut(),
    "cyberpunk": create_cyberpunk_lut(),
    "thermal": create_thermal_lut(),
    "matrix": create_matrix_lut(),
    "neon": create_neon_lut()
}

# Function to project 3D points to 2D based on a simple camera model
def project_points_to_2d(points, angle, canvas_width, canvas_height, top_view=False,
                          flip_x=False, flip_z=False, flip_y=False, elevation=30):
    # Make a copy to avoid modifying the original
    points_copy = points.copy()

    # Apply flips before projection
    if flip_x:
        points_copy[:, 0] = -points_copy[:, 0]  # Mirror X
    if flip_y:
        points_copy[:, 1] = -points_copy[:, 1]  # Flip Y up/down
    if flip_z:
        points_copy[:, 2] = -points_copy[:, 2]  # Reverse depth

    if top_view:
        # Top-down view - use X and Z as 2D coordinates
        # Apply a simple rotation around Y axis first
        theta = np.radians(angle)
        rot_matrix = np.array([
            [np.cos(theta), 0, np.sin(theta)],
            [0, 1, 0],
            [-np.sin(theta), 0, np.cos(theta)]
        ])
        points_copy = np.dot(points_copy, rot_matrix.T)

        # Project to 2D (top view: X and Z)
        x_2d = points_copy[:, 0]
        y_2d = points_copy[:, 2]

        # Normalize to canvas size with padding
        padding = 50
        min_x, max_x = np.min(x_2d), np.max(x_2d)
        min_y, max_y = np.min(y_2d), np.max(y_2d)

        width_range = max_x - min_x
        height_range = max_y - min_y

        # Calculate scale to fit in canvas
        scale_x = (canvas_width - 2*padding) / width_range if width_range > 0 else 1
        scale_y = (canvas_height - 2*padding) / height_range if height_range > 0 else 1

        # Use the smaller scale to maintain aspect ratio
        scale = min(scale_x, scale_y)

        # Center points in canvas
        center_x = (min_x + max_x) / 2
        center_y = (min_y + max_y) / 2

        x_2d = (x_2d - center_x) * scale + canvas_width / 2
        y_2d = (y_2d - center_y) * scale + canvas_height / 2

        # Calculate depth for point size and color
        depth = points_copy[:, 1]  # Y is depth in top view

    else:
        # Perspective view - first rotate around Y axis (azimuth)
        theta = np.radians(angle)
        rot_y_matrix = np.array([
            [np.cos(theta), 0, np.sin(theta)],
            [0, 1, 0],
            [-np.sin(theta), 0, np.cos(theta)]
        ])
        points_copy = np.dot(points_copy, rot_y_matrix.T)

        # Apply elevation angle (rotation around X axis)
        phi = np.radians(elevation)
        rot_x_matrix = np.array([
            [1, 0, 0],
            [0, np.cos(phi), -np.sin(phi)],
            [0, np.sin(phi), np.cos(phi)]
        ])
        points_copy = np.dot(points_copy, rot_x_matrix.T)

        # Simple perspective projection
        focal_length = 700
        z_offset = 1500  # Offset to push points back (with inverted Z, negative Z is away from camera)

        # Add offset to Z to push points back
        # Since Z is now inverted (negative is farther away), we subtract the offset
        points_copy[:, 2] = points_copy[:, 2] - z_offset
        
        # Instead of discarding points with Z ≥ 0 (behind camera), we'll keep all points
        # and handle them differently in the projection
        
        # Calculate depth values based on Z for all points (use absolute Z for depth)
        # This ensures proper depth sorting regardless of whether points are in front or behind
        depth = np.abs(points_copy[:, 2])
        
        # Separate front and back points
        front_mask = points_copy[:, 2] < 0
        back_mask = ~front_mask
        
        # Initialize arrays for all points
        x_2d = np.zeros(points_copy.shape[0])
        y_2d = np.zeros(points_copy.shape[0])
        
        # Process front points (normal projection)
        if np.any(front_mask):
            x_2d[front_mask] = focal_length * points_copy[front_mask, 0] / -points_copy[front_mask, 2]
            y_2d[front_mask] = focal_length * points_copy[front_mask, 1] / -points_copy[front_mask, 2]
        
        # Process back points - we invert the projection but the points remain "behind"
        if np.any(back_mask):
            # For points behind camera, invert the coordinates
            x_2d[back_mask] = -focal_length * points_copy[back_mask, 0] / points_copy[back_mask, 2]
            y_2d[back_mask] = -focal_length * points_copy[back_mask, 1] / points_copy[back_mask, 2]
        
        # If no valid points, return None
        if points_copy.shape[0] == 0:
            return None, None, None
            
        # Center in the canvas
        x_2d = x_2d + canvas_width / 2
        y_2d = -y_2d + canvas_height / 2  # Flip Y for screen coordinates (OpenCV origin is top-left)

    return x_2d, y_2d, depth

# Generate a frame showing available color modes
def create_help_frame(canvas_width, canvas_height):
    help_canvas = np.zeros((canvas_height, canvas_width, 3), dtype=np.uint8)

    # Title
    cv2.putText(help_canvas, "Artistic Point Cloud Controls", (30, 40),
                cv2.FONT_HERSHEY_SIMPLEX, 1.2, (255, 255, 255), 2)

    # Color mode examples
    y_pos = 100
    mode_labels = [
        "1: RGB Color Mode - Original colors",
        "2: Depth Mode - Rainbow coloring by depth",
        "3: Height Mode - Coloring by Y coordinate",
        "4: Cyberpunk Mode - Neon futuristic style",
        "5: Thermal Mode - Heat-map style visualization",
        "6: Matrix Mode - Green digital rain effect",
        "7: Neon Mode - Vibrant neon lights effect"
    ]

    for label in mode_labels:
        cv2.putText(help_canvas, label, (30, y_pos),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, (200, 200, 200), 1)
        y_pos += 40

    # Control keys
    y_pos += 40
    control_labels = [
        "r: Toggle auto-rotation",
        "t: Toggle top-down view",
        "p: Toggle particle effect",
        "m: Toggle motion trail effect",
        "c: Cycle colors (in non-RGB modes)",
        "+/-: Adjust point size",
        "x: Flip X axis (mirror left-right)",
        "y: Flip Y axis (upside-down)",
        "z: Flip Z axis (front-back)",
        "u/d: Adjust view elevation up/down",
        "h: Show/hide this help screen",
        "q: Quit"
    ]

    for label in control_labels:
        cv2.putText(help_canvas, label, (30, y_pos),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, (200, 200, 200), 1)
        y_pos += 40

    # Frame
    cv2.rectangle(help_canvas, (20, 20), (canvas_width-20, canvas_height-20),
                  (0, 120, 120), 2)

    return help_canvas

# Main loop
try:
    print("\nStarting artistic point cloud visualization with OpenCV...")
    print("Controls:")
    print("  - Press 'h' to show/hide help")
    print("  - Press '1-7' to change color modes")
    print("  - Press 'r' to toggle auto-rotation")
    print("  - Press 't' to toggle top-down view")
    print("  - Press 'p' to toggle particle effect")
    print("  - Press 'm' to toggle motion trail effect")
    print("  - Press 'c' to cycle colors")
    print("  - Press '+' or '-' to adjust point size")
    print("  - Press 'x' to flip X axis (mirror left-right)")
    print("  - Press 'y' to flip Y axis (upside-down)")
    print("  - Press 'z' to flip Z axis (front-back)")
    print("  - Press 'u'/'d' to adjust view elevation")
    print("  - Press 'q' to quit")

    # Create help frame
    help_frame = create_help_frame(canvas_width, canvas_height)
    show_help = False

    # For FPS calculation
    frame_count = 0
    start_time = time.time()
    fps = 0

    while True:
        frame_count += 1

        # Wait for new frames
        frames = listener.waitForNewFrame()
        color = frames["color"]
        depth = frames["depth"]

        # Get images as numpy arrays
        depth_data = depth.asarray()

        # Undistort and register
        registration.apply(color, depth, undistorted, registered)
        registered_data = registered.asarray(np.uint8)

        # Create coordinate grid (to avoid using loops)
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

            # Invert Z axis for more intuitive visualization
            # This makes depth increase away from the camera (positive Z is farther away)
            Z = -Z

            # NOTE: We don't need to invert Y - the Kinect calibration formula
            # already converts from pixel Y (downward) to world Y (upward)

            # Get RGB colors for valid points
            colors = registered_data[valid_y, valid_x, :3].copy()

            # Create points array
            points_3d = np.column_stack((X, Y, Z))

            # Project 3D points to 2D for visualization
            x_2d, y_2d, proj_depths = project_points_to_2d(
                points_3d, view_angle, canvas_width, canvas_height,
                top_view=top_view, flip_x=flip_x, flip_y=flip_y, flip_z=flip_z,
                elevation=view_elevation)

            if x_2d is not None:
                # Create a blank canvas
                canvas = np.zeros((canvas_height, canvas_width, 3), dtype=np.uint8)

                # For all colorful modes except original RGB
                if art_mode != "rgb":
                    # Normalize depths for coloring
                    if proj_depths is not None:
                        min_depth_val = np.min(proj_depths)
                        max_depth_val = np.max(proj_depths)

                        # Prevent division by zero
                        depth_range = max_depth_val - min_depth_val
                        if depth_range > 0:
                            norm_depths = ((proj_depths - min_depth_val) / depth_range * 255).astype(np.uint8)

                            # Apply color shift for cycling effect
                            if color_shift > 0:
                                norm_depths = (norm_depths + color_shift) % 256

                            # Apply appropriate color LUT
                            if art_mode == "depth":
                                colors = cv2.LUT(np.expand_dims(norm_depths, axis=1), color_luts["rainbow"])
                            elif art_mode == "height":
                                # Use Y values for height coloring
                                height_values = ((Y - np.min(Y)) / (np.max(Y) - np.min(Y) + 1e-10) * 255).astype(np.uint8)
                                colors = cv2.LUT(np.expand_dims(height_values, axis=1), color_luts["rainbow"])
                            elif art_mode == "cyberpunk":
                                colors = cv2.LUT(np.expand_dims(norm_depths, axis=1), color_luts["cyberpunk"])
                            elif art_mode == "thermal":
                                colors = cv2.LUT(np.expand_dims(norm_depths, axis=1), color_luts["thermal"])
                            elif art_mode == "matrix":
                                colors = cv2.LUT(np.expand_dims(norm_depths, axis=1), color_luts["matrix"])
                            elif art_mode == "neon":
                                colors = cv2.LUT(np.expand_dims(norm_depths, axis=1), color_luts["neon"])

                            colors = colors.reshape(-1, 3)

                # Sort points by depth for proper occlusion
                if proj_depths is not None and not top_view:
                    # Sort from back to front for painter's algorithm
                    sort_idx = np.argsort(proj_depths)
                    x_2d = x_2d[sort_idx]
                    y_2d = y_2d[sort_idx]
                    colors = colors[sort_idx]
                    proj_depths = proj_depths[sort_idx]

                # Draw points
                num_points = len(x_2d)
                points_to_draw = min(num_points, 10000)  # Limit for performance

                # Calculate distance-based point size if needed
                point_sizes = np.ones(points_to_draw) * point_size
                if not top_view and proj_depths is not None:
                    # Make closer points larger
                    normalized_depths = 1.0 - (proj_depths[:points_to_draw] - np.min(proj_depths)) / (np.max(proj_depths) - np.min(proj_depths) + 1e-10)
                    point_sizes = point_size * (0.5 + normalized_depths)

                # Draw points
                for i in range(points_to_draw):
                    x, y = int(x_2d[i]), int(y_2d[i])

                    # Skip points outside canvas
                    if x < 0 or x >= canvas_width or y < 0 or y >= canvas_height:
                        continue

                    # Apply particle effect
                    if particle_effect:
                        # Add randomness to positions
                        random_offset = np.random.randint(-3, 4, 2)
                        x += random_offset[0]
                        y += random_offset[1]

                        # Skip if now outside canvas
                        if x < 0 or x >= canvas_width or y < 0 or y >= canvas_height:
                            continue

                    # Calculate point size for this point
                    ps = max(1, int(point_sizes[i]))

                    # Draw circle for each point
                    color = colors[i].tolist()
                    cv2.circle(canvas, (x, y), ps, color, -1)

                # Apply temporal blending if enabled
                if temporal_blend > 0 and previous_frame is not None:
                    canvas = cv2.addWeighted(canvas, 1.0, previous_frame, temporal_blend, 0)

                # Add info text
                elapsed = time.time() - start_time
                if elapsed >= 1.0:
                    fps = frame_count / elapsed
                    frame_count = 0
                    start_time = time.time()
                    
                pause_status = "PAUSED" if paused else ""
                info_text = f"Mode: {art_mode} | Points: {num_points} | FPS: {fps:.1f} | Size: {point_size} {pause_status}"
                cv2.putText(canvas, info_text, (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 1)

                # Show either the visualization or help screen
                if show_help:
                    cv2.imshow("Artistic Point Cloud", help_frame)
                else:
                    cv2.imshow("Artistic Point Cloud", canvas)
                    previous_frame = canvas.copy()

                # Update auto-rotation
                if auto_rotate and not paused:
                    view_angle = (view_angle + rotation_speed) % 360

            else:
                # No valid points to draw
                canvas = np.zeros((canvas_height, canvas_width, 3), dtype=np.uint8)
                cv2.putText(canvas, "No valid points in view", (canvas_width//2 - 100, canvas_height//2),
                           cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
                cv2.imshow("Artistic Point Cloud", canvas)

        # Release frames
        listener.release(frames)

        # Handle keyboard input
        key = cv2.waitKey(1) & 0xFF
        if key == ord('q'):
            break
        elif key == ord('h'):
            show_help = not show_help
        elif key == ord('1'):
            art_mode = "rgb"
        elif key == ord('2'):
            art_mode = "depth"
        elif key == ord('3'):
            art_mode = "height"
        elif key == ord('4'):
            art_mode = "cyberpunk"
        elif key == ord('5'):
            art_mode = "thermal"
        elif key == ord('6'):
            art_mode = "matrix"
        elif key == ord('7'):
            art_mode = "neon"
        elif key == ord('r'):
            auto_rotate = not auto_rotate
        elif key == ord('t'):
            top_view = not top_view
        elif key == ord('p'):
            particle_effect = not particle_effect
        elif key == ord('m'):
            # Toggle motion trail
            if temporal_blend == 0:
                temporal_blend = 0.3
            else:
                temporal_blend = 0
        elif key == ord('c'):
            # Cycle colors
            color_shift = (color_shift + 50) % 256
        elif key == ord('+') or key == ord('='):
            point_size = min(point_size + 1, 10)
        elif key == ord('-'):
            point_size = max(point_size - 1, 1)
        elif key == ord('x'):
            # Flip X axis (mirror left-right)
            flip_x = not flip_x
        elif key == ord('y'):
            # Flip Y axis (upside down)
            flip_y = not flip_y
        elif key == ord('z'):
            # Flip Z axis (front-back)
            flip_z = not flip_z
        elif key == ord('u'):
            # Increase view elevation
            view_elevation = min(view_elevation + 5, 90)
        elif key == ord('d'):
            # Decrease view elevation
            view_elevation = max(view_elevation - 5, -90)
        elif key == ord(' '):
            # Toggle pause with spacebar
            paused = not paused

except KeyboardInterrupt:
    print("\nInterrupted by user")
except Exception as e:
    print(f"\nError: {e}")
finally:
    # Stop and close device
    device.stop()
    device.close()

    # Close all windows
    cv2.destroyAllWindows()

    print("Artistic point cloud viewer closed")