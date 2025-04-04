#!/usr/bin/env python
# Artistic Kinect Point Cloud Visualizer using PyVista
# Alternative implementation when Open3D has GLFW conflicts

import numpy as np
import cv2
import sys
import time
import threading
import copy
from pylibfreenect2 import Freenect2, SyncMultiFrameListener
from pylibfreenect2 import FrameType, Registration, Frame
from pylibfreenect2 import createConsoleLogger, setGlobalLogger
from pylibfreenect2 import LoggerLevel

# Try importing PyVista for visualization
try:
    import pyvista as pv
    has_pyvista = True
except ImportError:
    has_pyvista = False
    print("PyVista not found. Please install with: pip install pyvista")
    print("Falling back to optimized matplotlib visualization")
    import matplotlib.pyplot as plt
    from mpl_toolkits.mplot3d import Axes3D

# Try importing matplotlib for color maps
try:
    import matplotlib.cm as cm
    has_matplotlib = True
except ImportError:
    has_matplotlib = False

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

# Global variables for visualization thread
latest_points = None
latest_colors = None
running = True
art_mode = "rgb"
point_size = 5
auto_rotate = True

# Define custom color maps
color_maps = {
    "rainbow": lambda t: np.array([np.sin(2*np.pi*t), np.sin(2*np.pi*(t+1/3)), np.sin(2*np.pi*(t+2/3))]) * 0.5 + 0.5,
    "cyberpunk": lambda t: np.array([
        0.8 * np.sin(np.pi * t) + 0.2,
        0.5 * np.sin(np.pi * (t + 0.5)) + 0.5,
        np.cos(np.pi * t) ** 2
    ]),
    "sunset": lambda t: np.array([
        np.clip(1.5 - 1.5 * t, 0, 1),
        np.clip(1.5 * t - 0.5, 0, 1) * np.clip(2.5 - 2.5 * t, 0, 1),
        np.clip(2 * t - 1.5, 0, 1)
    ]),
}

# Apply custom color map
def apply_color_map(values, cmap_name="rainbow"):
    if cmap_name in color_maps:
        cmap_func = color_maps[cmap_name]
        normalized = (values - np.min(values)) / (np.max(values) - np.min(values) + 1e-10)
        colors = np.zeros((len(values), 3))
        for i, t in enumerate(normalized):
            colors[i] = cmap_func(t)
        return colors
    elif has_matplotlib:
        colormap = getattr(cm, cmap_name, cm.viridis)
        normalized = (values - np.min(values)) / (np.max(values) - np.min(values) + 1e-10)
        return colormap(normalized)[:, :3]
    else:
        # Fallback to simple rainbow
        normalized = (values - np.min(values)) / (np.max(values) - np.min(values) + 1e-10)
        colors = np.zeros((len(values), 3))
        colors[:, 0] = np.clip(1.5 - 1.5 * normalized, 0, 1)  # R
        colors[:, 1] = np.clip(1.5 * normalized - 0.5, 0, 1) * np.clip(2.5 - 2.5 * normalized, 0, 1)  # G
        colors[:, 2] = np.clip(2 * normalized - 1.5, 0, 1)  # B
        return colors

# Update point cloud colors based on artistic mode
def update_colors(points, orig_colors):
    if art_mode == "rgb":
        return orig_colors
    elif art_mode == "depth":
        depths = points[:, 2]  # Z coordinate
        return apply_color_map(depths, "cool")
    elif art_mode == "height":
        heights = points[:, 1]  # Y coordinate
        return apply_color_map(heights, "plasma")
    elif art_mode == "distance":
        distances = np.sqrt(points[:, 0]**2 + points[:, 2]**2)  # XZ distance
        return apply_color_map(distances, "viridis")
    elif art_mode == "cyberpunk":
        heights = points[:, 1]  # Y coordinate
        return apply_color_map(heights, "cyberpunk")
    elif art_mode == "sunset":
        depths = points[:, 2]  # Z coordinate
        return apply_color_map(depths, "sunset")
    else:
        return orig_colors

# PyVista visualization thread
def pyvista_thread():
    global latest_points, latest_colors, running, art_mode, point_size, auto_rotate
    
    # Create plotter
    plotter = pv.Plotter(title="Artistic Kinect Point Cloud", window_size=[1280, 720])
    
    # Create empty point cloud
    cloud = pv.PolyData()
    actor = None
    
    # Setup initial view
    plotter.camera_position = [(0, 0, -3000), (0, 0, 0), (0, -1, 0)]
    plotter.set_background("black")
    
    # Add key press callbacks
    def key_callback(key):
        global art_mode, point_size, auto_rotate
        if key == "1":
            art_mode = "rgb"
        elif key == "2":
            art_mode = "depth"
        elif key == "3":
            art_mode = "height" 
        elif key == "4":
            art_mode = "distance"
        elif key == "5":
            art_mode = "cyberpunk"
        elif key == "6":
            art_mode = "sunset"
        elif key == "plus" or key == "equal":
            point_size = min(point_size + 1, 20)
        elif key == "minus":
            point_size = max(point_size - 1, 1)
        elif key == "r":
            auto_rotate = not auto_rotate
        elif key == "q":
            running = False
            plotter.close()
        
    plotter.add_key_event("1", lambda: key_callback("1"))
    plotter.add_key_event("2", lambda: key_callback("2"))
    plotter.add_key_event("3", lambda: key_callback("3"))
    plotter.add_key_event("4", lambda: key_callback("4"))
    plotter.add_key_event("5", lambda: key_callback("5"))
    plotter.add_key_event("6", lambda: key_callback("6"))
    plotter.add_key_event("plus", lambda: key_callback("plus"))
    plotter.add_key_event("minus", lambda: key_callback("minus"))
    plotter.add_key_event("equal", lambda: key_callback("equal"))
    plotter.add_key_event("r", lambda: key_callback("r"))
    plotter.add_key_event("q", lambda: key_callback("q"))
    
    # Make interactor style trackball
    plotter.enable_trackball_style()
    
    # Add text showing current mode
    text_actor = plotter.add_text(f"Mode: {art_mode} | Points: 0", position=(10, 10),
                                 font_size=14, color="white")
    
    # Initialize time and frame count
    start_time = time.time()
    frame_count = 0
    fps = 0
    
    # Show instructions
    instructions = [
        "Controls:",
        "- 1: RGB color mode",
        "- 2: Depth color mode",
        "- 3: Height color mode",
        "- 4: Distance color mode",
        "- 5: Cyberpunk colors",
        "- 6: Sunset colors",
        "- +/-: Adjust point size",
        "- r: Toggle auto-rotation",
        "- q: Quit"
    ]
    
    y_pos = 50
    for line in instructions:
        plotter.add_text(line, position=(10, y_pos), font_size=12, color="white")
        y_pos += 20
    
    # Interactive rendering loop
    plotter.show(interactive=False, auto_close=False)
    
    try:
        while running and plotter.is_active:
            if latest_points is not None and len(latest_points) > 0:
                # Make a copy to avoid threading issues
                points = latest_points.copy()
                orig_colors = latest_colors.copy()
                
                # Update colors based on selected mode
                colors = update_colors(points, orig_colors)
                
                # Create or update point cloud
                cloud.points = points
                cloud["rgb"] = (colors * 255).astype(np.uint8)
                
                # Remove existing actor and add new one
                plotter.remove_actor(actor)
                actor = plotter.add_mesh(cloud, render_points_as_spheres=True, 
                                       point_size=point_size, rgb=True)
                
                # Update text
                frame_count += 1
                elapsed = time.time() - start_time
                if elapsed >= 1.0:
                    fps = frame_count / elapsed
                    frame_count = 0
                    start_time = time.time()
                
                plotter.textActors[0].SetInput(
                    f"Mode: {art_mode} | Points: {len(points)} | FPS: {fps:.1f} | Point Size: {point_size}"
                )
                
                # Auto-rotation
                if auto_rotate:
                    plotter.camera.azimuth += 0.5
                
                # Update render window
                plotter.update()
            else:
                # Small delay if no points are available
                time.sleep(0.01)
                plotter.update()
    
    except Exception as e:
        print(f"Visualization error: {e}")
    finally:
        plotter.close()

# Matplotlib visualization thread (fallback)
def matplotlib_thread():
    global latest_points, latest_colors, running, art_mode, point_size, auto_rotate
    
    # Setup matplotlib
    plt.ion()  # Enable interactive mode
    fig = plt.figure(figsize=(10, 8))
    ax = fig.add_subplot(111, projection='3d')
    
    # Set fixed view limits
    ax.set_xlim(-2000, 2000)
    ax.set_ylim(-2000, 2000)
    ax.set_zlim(0, 4500)
    
    # Set labels and title
    ax.set_xlabel('X (mm)')
    ax.set_ylabel('Y (mm)')
    ax.set_zlabel('Z (mm)')
    ax.set_title(f'Kinect Point Cloud - Mode: {art_mode}')
    
    # Initial empty scatter plot
    scatter = None
    rotation_angle = 0
    display_step = 5  # Display every Nth point for Matplotlib (performance)
    
    # Add text for controls
    plt.figtext(0.01, 0.01, "Controls: 1-6: Change color mode, +/-: Point size, r: Rotation, q: Quit", 
               fontsize=8)
    
    # Main loop
    frame_count = 0
    start_time = time.time()
    fps = 0
    
    try:
        while running:
            if latest_points is not None and len(latest_points) > 0:
                # Make a copy to avoid threading issues
                points = latest_points.copy()
                orig_colors = latest_colors.copy()
                
                # Downsample for matplotlib (it's slow with too many points)
                if len(points) > display_step:
                    idx = np.arange(0, len(points), display_step)
                    display_points = points[idx]
                    display_colors = orig_colors[idx] if orig_colors is not None else None
                else:
                    display_points = points
                    display_colors = orig_colors
                
                # Update colors based on selected mode
                colors = update_colors(display_points, display_colors)
                
                # Extract X, Y, Z coordinates
                xs = display_points[:, 0]
                ys = display_points[:, 1]
                zs = display_points[:, 2]
                
                # Update scatter plot
                if scatter is None:
                    scatter = ax.scatter(xs, ys, zs, c=colors, s=point_size)
                else:
                    scatter._offsets3d = (xs, ys, zs)
                    scatter.set_color(colors)
                
                # Update title with point count and FPS
                frame_count += 1
                elapsed = time.time() - start_time
                if elapsed >= 1.0:
                    fps = frame_count / elapsed
                    frame_count = 0
                    start_time = time.time()
                
                ax.set_title(f'Kinect Point Cloud - Mode: {art_mode} | Points: {len(display_points)} | FPS: {fps:.1f}')
                
                # Auto-rotation
                if auto_rotate and frame_count % 3 == 0:
                    rotation_angle = (rotation_angle + 1) % 360
                    ax.view_init(elev=30, azim=rotation_angle)
                
                # Draw and process events
                fig.canvas.draw_idle()
                plt.pause(0.001)
                
                # Check if figure is still open
                if not plt.fignum_exists(fig.number):
                    running = False
                    break
            
            else:
                # Small delay if no points are available
                plt.pause(0.1)
            
            # Check for key events (via cv2)
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
                art_mode = "cyberpunk"
            elif key == ord('6'):
                art_mode = "sunset"
            elif key == ord('+') or key == ord('='):
                point_size = min(point_size + 1, 20)
            elif key == ord('-') or key == ord('_'):
                point_size = max(point_size - 1, 1)
            elif key == ord('r'):
                auto_rotate = not auto_rotate
    
    except Exception as e:
        print(f"Visualization error: {e}")
    finally:
        plt.close('all')

# Function to acquire frames and process point cloud
def process_frames():
    global latest_points, latest_colors, running
    
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
                
                # Update global point cloud data
                latest_points = np.column_stack((X, Y, Z))
                latest_colors = colors
            
            # Release frames
            listener.release(frames)
            
            # Check for quit key
            key = cv2.waitKey(1) & 0xFF
            if key == ord('q'):
                running = False
                break
    
    except KeyboardInterrupt:
        running = False
    except Exception as e:
        print(f"Frame processing error: {e}")
        running = False

if __name__ == "__main__":
    print("\nStarting artistic point cloud visualization with PyVista...")
    print("Controls:")
    print("  - Press 'q' to exit")
    print("  - Press '1' for RGB color mode")
    print("  - Press '2' for depth-based color mode")
    print("  - Press '3' for height-based color mode")
    print("  - Press '4' for distance-based color mode")
    print("  - Press '5' for cyberpunk color mode")
    print("  - Press '6' for sunset color mode")
    print("  - Press '+'/'-' to adjust point size")
    print("  - Press 'r' to toggle auto-rotation")
    
    try:
        # Start data acquisition thread
        process_thread = threading.Thread(target=process_frames)
        process_thread.daemon = True
        process_thread.start()
        
        # Start visualization thread
        if has_pyvista:
            print("Using PyVista for visualization")
            vis_thread = threading.Thread(target=pyvista_thread)
        else:
            print("Falling back to Matplotlib for visualization")
            vis_thread = threading.Thread(target=matplotlib_thread)
        
        vis_thread.daemon = True
        vis_thread.start()
        
        # Wait for visualization to complete
        while running:
            time.sleep(0.1)
    
    except KeyboardInterrupt:
        print("\nInterrupted by user. Closing...")
    finally:
        # Make sure everything is cleaned up
        running = False
        
        # Wait for threads to terminate
        if process_thread.is_alive():
            process_thread.join(timeout=1.0)
        if vis_thread.is_alive():
            vis_thread.join(timeout=1.0)
        
        # Stop and close device
        device.stop()
        device.close()
        
        # Close any remaining OpenCV windows
        cv2.destroyAllWindows()
        
        print("Artistic point cloud viewer closed")
