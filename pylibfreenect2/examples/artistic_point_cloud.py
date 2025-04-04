#!/usr/bin/env python
# Artistic Kinect Point Cloud Visualizer using Open3D
# This script provides high-performance point cloud visualization with artistic effects

import numpy as np
import cv2
import sys
import time
import open3d as o3d
from pylibfreenect2 import Freenect2, SyncMultiFrameListener
from pylibfreenect2 import FrameType, Registration, Frame
from pylibfreenect2 import createConsoleLogger, setGlobalLogger
from pylibfreenect2 import LoggerLevel
import threading
import copy

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
point_step = 4      # Take every Nth point (can be smaller with Open3D)

# Get the depth camera intrinsic parameters
depth_params = device.getIrCameraParams()
fx = depth_params.fx
fy = depth_params.fy
cx = depth_params.cx
cy = depth_params.cy

print(f"Depth camera parameters: fx={fx}, fy={fy}, cx={cx}, cy={cy}")

# Global variables for visualization thread
latest_pcd = None
running = True
vis = None
render_lock = threading.Lock()

# Artistic parameters
art_mode = "rgb"       # Default artistic mode
point_size = 3.0       # Point size
dynamic_pts = False    # Enable "breathing" point size
trail_effect = False   # Enable trail effect
pcd_rotation = True    # Auto-rotate point cloud
ripple_effect = False  # Water ripple effect
trails = []            # List to hold previous frames for trails
motion_blur = 0        # Motion blur strength (0-10)
palette = "default"    # Color palette

# Initialize colorblind-friendly palettes
color_palettes = {
    "default": None,  # Uses original colors
    "viridis": None,  # Will be initialized with matplotlib viridis
    "plasma": None,   # Will be initialized with matplotlib plasma
    "cyberpunk": np.array([
        [0, 255, 255],    # Cyan
        [255, 0, 255],    # Magenta
        [255, 255, 0],    # Yellow
        [0, 255, 128]     # Teal
    ]) / 255.0,
    "sunset": np.array([
        [255, 0, 0],      # Red
        [255, 128, 0],    # Orange
        [255, 200, 0],    # Yellow
        [128, 0, 64]      # Burgundy
    ]) / 255.0,
    "monochrome": np.array([
        [255, 255, 255],  # White
        [200, 200, 200],  # Light gray
        [150, 150, 150],  # Mid gray
        [100, 100, 100]   # Dark gray
    ]) / 255.0
}

# Try to import matplotlib for some color palettes
try:
    import matplotlib.pyplot as plt
    viridis_cmap = plt.cm.viridis
    plasma_cmap = plt.cm.plasma
    colors_viridis = viridis_cmap(np.linspace(0, 1, 256))[:, :3]
    colors_plasma = plasma_cmap(np.linspace(0, 1, 256))[:, :3]
    color_palettes["viridis"] = colors_viridis
    color_palettes["plasma"] = colors_plasma
except ImportError:
    print("Matplotlib not available, some color palettes will be unavailable")


def apply_palette(colors, palette_name):
    """Apply a color palette to the point cloud colors"""
    if palette_name == "default" or palette_name not in color_palettes:
        return colors
    
    palette_colors = color_palettes[palette_name]
    if palette_colors is None:
        return colors
    
    # For matplotlib-based palettes
    if len(palette_colors) > 10:  # Assuming these are the matplotlib ones with 256 colors
        # Map depth values to palette indices
        depths = np.linalg.norm(colors, axis=1)
        normalized_depths = (depths - np.min(depths)) / (np.max(depths) - np.min(depths) + 1e-10)
        palette_indices = (normalized_depths * (len(palette_colors) - 1)).astype(int)
        return palette_colors[palette_indices]
    
    # For custom palettes with a few colors
    else:
        num_points = len(colors)
        num_palette_colors = len(palette_colors)
        # Randomly assign palette colors to points
        palette_indices = np.random.randint(0, num_palette_colors, size=num_points)
        return palette_colors[palette_indices]


def apply_artistic_effects(pcd, frame_count):
    """Apply various artistic effects to the point cloud"""
    global point_size, dynamic_pts, art_mode, palette
    
    # Get points and colors
    points = np.asarray(pcd.points)
    colors = np.asarray(pcd.colors)
    
    # Apply different color modes
    if art_mode == "rgb":
        # RGB colors are already set
        pass
    elif art_mode == "depth":
        # Color based on depth (Z coordinate)
        depths = points[:, 2]
        min_z, max_z = min_depth, max_depth
        normalized_depths = (depths - min_z) / (max_z - min_z)
        
        # Red to blue gradient based on depth
        new_colors = np.zeros_like(colors)
        new_colors[:, 0] = 1.0 - normalized_depths  # Red channel (inverse with depth)
        new_colors[:, 2] = normalized_depths        # Blue channel
        colors = new_colors
    elif art_mode == "height":
        # Color based on height (Y coordinate)
        heights = points[:, 1]
        min_y, max_y = np.min(heights), np.max(heights)
        normalized_heights = (heights - min_y) / (max_y - min_y + 1e-10)
        
        # Create height-based rainbow gradient
        new_colors = np.zeros_like(colors)
        # Red-Green-Blue gradient based on height
        new_colors[:, 0] = np.clip(1.0 - 2 * np.abs(normalized_heights - 0.25), 0, 1)
        new_colors[:, 1] = np.clip(1.0 - 2 * np.abs(normalized_heights - 0.5), 0, 1)
        new_colors[:, 2] = np.clip(1.0 - 2 * np.abs(normalized_heights - 0.75), 0, 1)
        colors = new_colors
    elif art_mode == "distance":
        # Color based on distance from origin (in XZ plane)
        distances = np.sqrt(points[:, 0]**2 + points[:, 2]**2)
        max_dist = np.max(distances)
        normalized_distances = distances / max_dist
        
        # Apply a hot-cold gradient
        new_colors = np.zeros_like(colors)
        new_colors[:, 0] = normalized_distances  # Red increases with distance
        new_colors[:, 2] = 1.0 - normalized_distances  # Blue decreases with distance
        colors = new_colors
    elif art_mode == "silhouette":
        # Edge detection - highlight silhouette edges
        edge_mask = detect_edges(points)
        new_colors = np.zeros_like(colors)
        new_colors[edge_mask] = [1.0, 1.0, 1.0]  # White edges
        colors = new_colors
    
    # Apply selected color palette
    if palette != "default":
        colors = apply_palette(colors, palette)
    
    # Update colors in point cloud
    pcd.colors = o3d.utility.Vector3dVector(colors)
    
    # Dynamic point size effect ("breathing")
    if dynamic_pts:
        new_size = 2.0 + 2.0 * np.sin(frame_count * 0.05)
        point_size = new_size
    
    # Apply ripple effect
    if ripple_effect:
        ripple_points = np.array(pcd.points)
        time_factor = frame_count * 0.1
        center_x, center_z = 0, 2000  # Center of ripple
        
        # Calculate distance from center in xz plane
        dx = ripple_points[:, 0] - center_x
        dz = ripple_points[:, 2] - center_z
        distances = np.sqrt(dx**2 + dz**2)
        
        # Apply sine wave based on distance and time
        wave_height = 30.0  # Maximum displacement
        wave_frequency = 0.001  # Spatial frequency
        ripple_points[:, 1] += wave_height * np.sin(distances * wave_frequency - time_factor)
        
        # Update point positions
        pcd.points = o3d.utility.Vector3dVector(ripple_points)
    
    return pcd


def detect_edges(points, threshold=100.0):
    """Detect edges in the point cloud based on depth discontinuities"""
    # Convert points to depth image (top-down view)
    z_values = points[:, 2]
    x_values = points[:, 0]
    y_values = points[:, 1]
    
    # Create a grid to project points onto
    grid_size = 512
    depth_image = np.zeros((grid_size, grid_size))
    
    # Normalize coordinates to grid
    x_min, x_max = np.min(x_values), np.max(x_values)
    z_min, z_max = np.min(z_values), np.max(z_values)
    
    # Map points to grid
    x_norm = ((x_values - x_min) / (x_max - x_min + 1e-10) * (grid_size-1)).astype(int)
    z_norm = ((z_values - z_min) / (z_max - z_min + 1e-10) * (grid_size-1)).astype(int)
    
    # Clip to ensure valid indices
    x_norm = np.clip(x_norm, 0, grid_size-1)
    z_norm = np.clip(z_norm, 0, grid_size-1)
    
    # Fill depth image with Y values
    for i in range(len(points)):
        depth_image[z_norm[i], x_norm[i]] = y_values[i]
    
    # Apply Sobel operator for edge detection
    sobelx = cv2.Sobel(depth_image, cv2.CV_64F, 1, 0, ksize=3)
    sobely = cv2.Sobel(depth_image, cv2.CV_64F, 0, 1, ksize=3)
    gradient_magnitude = np.sqrt(sobelx**2 + sobely**2)
    
    # Create edge mask based on gradient threshold
    edge_mask = gradient_magnitude > threshold
    
    # Map back to point cloud indices
    point_mask = np.zeros(len(points), dtype=bool)
    for i in range(len(points)):
        if edge_image[z_norm[i], x_norm[i]]:
            point_mask[i] = True
    
    return point_mask


def visualization_thread():
    global latest_pcd, running, vis, render_lock, point_size, art_mode
    
    # Create visualizer
    vis = o3d.visualization.Visualizer()
    vis.create_window(window_name="Artistic Kinect Point Cloud", width=1280, height=720)
    
    # Set render options
    render_option = vis.get_render_option()
    render_option.background_color = np.array([0.0, 0.0, 0.0])  # Black background
    render_option.point_size = point_size
    
    # Initialize empty point cloud
    pcd = o3d.geometry.PointCloud()
    vis.add_geometry(pcd)
    
    # Setup camera view
    view_control = vis.get_view_control()
    view_control.set_zoom(0.5)
    
    frame_count = 0
    last_update_time = time.time()
    fps_count = 0
    fps = 0
    
    while running:
        frame_count += 1
        fps_count += 1
        current_time = time.time()
        
        # Calculate FPS every second
        if current_time - last_update_time >= 1.0:
            fps = fps_count / (current_time - last_update_time)
            fps_count = 0
            last_update_time = current_time
            print(f"\rFPS: {fps:.1f} - Mode: {art_mode}", end="")
        
        # Update point cloud if new data is available
        with render_lock:
            if latest_pcd is not None:
                # Make a copy to avoid threading issues
                pcd_copy = copy.deepcopy(latest_pcd)
                
                # Apply artistic effects
                pcd_copy = apply_artistic_effects(pcd_copy, frame_count)
                
                # Trail effect (motion blur)
                if trail_effect and motion_blur > 0:
                    # Add current point cloud to trails
                    trails.append(pcd_copy)
                    if len(trails) > motion_blur:
                        trails.pop(0)  # Remove oldest frame
                    
                    # Combine all trails with decreasing opacity
                    points = []
                    colors = []
                    for i, trail_pcd in enumerate(trails):
                        trail_points = np.asarray(trail_pcd.points)
                        trail_colors = np.asarray(trail_pcd.colors)
                        
                        # Reduce opacity for older frames
                        alpha = (i + 1) / len(trails)
                        trail_colors = trail_colors * alpha
                        
                        points.append(trail_points)
                        colors.append(trail_colors)
                    
                    # Combine all trails
                    if points:
                        pcd_copy.points = o3d.utility.Vector3dVector(np.vstack(points))
                        pcd_copy.colors = o3d.utility.Vector3dVector(np.vstack(colors))
                
                # Update the point cloud in the visualizer
                vis.remove_geometry(pcd)
                pcd = pcd_copy
                vis.add_geometry(pcd)
            
            # Update render options in case they've changed
            render_option.point_size = point_size
            
            # Auto-rotation
            if pcd_rotation:
                view_control = vis.get_view_control()
                current_params = view_control.convert_to_pinhole_camera_parameters()
                current_extrinsic = current_params.extrinsic
                
                # Create rotation matrix around y-axis
                angle_rad = np.radians(0.5)  # Small rotation angle
                rot_mat = np.array([
                    [np.cos(angle_rad), 0, np.sin(angle_rad), 0],
                    [0, 1, 0, 0],
                    [-np.sin(angle_rad), 0, np.cos(angle_rad), 0],
                    [0, 0, 0, 1]
                ])
                
                # Apply rotation
                new_extrinsic = np.dot(current_extrinsic, rot_mat)
                current_params.extrinsic = new_extrinsic
                view_control.convert_from_pinhole_camera_parameters(current_params)
        
        # Update visualization
        vis.update_geometry(pcd)
        vis.poll_events()
        vis.update_renderer()
        
        # Sleep a bit to reduce CPU usage
        time.sleep(0.01)
    
    # Clean up visualizer
    vis.destroy_window()


def process_frames():
    global latest_pcd, running, render_lock, art_mode, point_size, dynamic_pts, trail_effect, palette, pcd_rotation, ripple_effect, motion_blur
    
    try:
        while running:
            # Wait for new frames
            frames = listener.waitForNewFrame()
            color = frames["color"]
            depth = frames["depth"]
            
            # Get images as numpy arrays
            depth_data = depth.asarray()
            
            # Undistort and register
            registration.apply(color, depth, undistorted, registered)
            registered_data = registered.asarray(np.uint8)
            
            # Create arrays for point cloud data using NumPy operations
            # Generate coordinate grid with point_step spacing
            y_indices, x_indices = np.mgrid[0:424:point_step, 0:512:point_step]
            y_indices = y_indices.flatten()
            x_indices = x_indices.flatten()
            
            # Get depth values for all sampled points
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
                
                # Get RGB colors for valid points
                colors = registered_data[valid_y, valid_x, :3].astype(float) / 255.0
                # Convert BGR to RGB
                colors = colors[:, [2, 1, 0]]
                
                # Create Open3D point cloud
                pcd = o3d.geometry.PointCloud()
                points = np.column_stack((X, Y, Z))
                pcd.points = o3d.utility.Vector3dVector(points)
                pcd.colors = o3d.utility.Vector3dVector(colors)
                
                # Update the point cloud for visualization thread
                with render_lock:
                    latest_pcd = pcd
            
            # Release frames
            listener.release(frames)
            
            # Check for key presses (using cv2 for keyboard input)
            key = cv2.waitKey(1) & 0xFF
            if key == ord('q'):
                running = False
                break
            elif key == ord('1'):
                art_mode = "rgb"
            elif key == ord('2'):
                art_mode = "depth"
            elif key == ord('3'):
                art_mode = "height"
            elif key == ord('4'):
                art_mode = "distance"
            elif key == ord('5'):
                art_mode = "silhouette"
            elif key == ord('+') or key == ord('='):
                point_size = min(point_size + 0.5, 10.0)
            elif key == ord('-') or key == ord('_'):
                point_size = max(point_size - 0.5, 1.0)
            elif key == ord('d'):
                dynamic_pts = not dynamic_pts
            elif key == ord('t'):
                trail_effect = not trail_effect
            elif key == ord('r'):
                pcd_rotation = not pcd_rotation
            elif key == ord('w'):
                ripple_effect = not ripple_effect
            elif key == ord('p'):
                # Cycle through palettes
                palettes = list(color_palettes.keys())
                current_idx = palettes.index(palette)
                palette = palettes[(current_idx + 1) % len(palettes)]
            elif key == ord('m'):
                # Adjust motion blur
                motion_blur = (motion_blur + 1) % 11
    
    except KeyboardInterrupt:
        print("\nInterrupted by user")
    except Exception as e:
        print(f"\nError: {e}")
    finally:
        running = False


if __name__ == "__main__":
    print("Starting artistic point cloud visualization with Open3D...")
    print("Controls:")
    print("  - Press 'q' to exit")
    print("  - Press '1' for RGB color mode")
    print("  - Press '2' for depth-based color mode")
    print("  - Press '3' for height-based color mode")
    print("  - Press '4' for distance-based color mode")
    print("  - Press '5' for silhouette mode")
    print("  - Press '+'/'-' to adjust point size")
    print("  - Press 'd' to toggle dynamic point size (breathing effect)")
    print("  - Press 't' to toggle trail effect")
    print("  - Press 'r' to toggle auto-rotation")
    print("  - Press 'w' to toggle ripple wave effect")
    print("  - Press 'p' to cycle through color palettes")
    print("  - Press 'm' to adjust motion blur strength")
    
    try:
        # Start visualization in a separate thread
        vis_thread = threading.Thread(target=visualization_thread)
        vis_thread.daemon = True
        vis_thread.start()
        
        # Process frames in the main thread
        process_frames()
    
    except KeyboardInterrupt:
        print("\nInterrupted by user. Closing...")
    finally:
        # Make sure everything is cleaned up
        running = False
        if vis_thread.is_alive():
            vis_thread.join(timeout=1.0)
        
        # Stop and close device
        device.stop()
        device.close()
        
        # Close any remaining OpenCV windows
        cv2.destroyAllWindows()
        
        print("Artistic point cloud viewer closed")
