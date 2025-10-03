#!/usr/bin/env python
"""
Kinect v2 to TouchDesigner via Syphon
======================================

Sends properly aligned point cloud data to TouchDesigner using Syphon.
Uses libfreenect2's registration for correct undistortion.

Output format:
- XYZ point cloud as 512x424 texture
- RGB channels contain X, Y, Z coordinates
- Alpha channel = 1.0 for valid points, 0.0 for invalid

TouchDesigner Setup:
1. Syphon In TOP → server name "KinectPointCloud"
2. Connect to pointRender component input 1
3. Connect RGB Syphon "KinectRGB" to pointRender input 2

Requirements:
    pip install syphon-python numpy

Usage:
    python kinect_syphon_sender.py
"""

import sys
import numpy as np
from pylibfreenect2 import Freenect2, SyncMultiFrameListener
from pylibfreenect2 import FrameType, Registration, Frame
from pylibfreenect2 import createConsoleLogger, setGlobalLogger, LoggerLevel

try:
    import syphon
    from syphon.utils.raw import create_mtl_texture
    from syphon.utils.numpy import copy_image_to_mtl_texture
    HAS_SYPHON = True
except ImportError:
    print("ERROR: syphon-python not installed")
    print("Install with: pip install syphon-python")
    sys.exit(1)

# Reduce logging
logger = createConsoleLogger(LoggerLevel.Warning)
setGlobalLogger(logger)

# Initialize Kinect
print("Initializing Kinect v2...")
try:
    from pylibfreenect2 import OpenGLPacketPipeline
    pipeline = OpenGLPacketPipeline()
    print("Using: OpenGLPacketPipeline")
except:
    try:
        from pylibfreenect2 import OpenCLPacketPipeline
        pipeline = OpenCLPacketPipeline()
        print("Using: OpenCLPacketPipeline")
    except:
        from pylibfreenect2 import CpuPacketPipeline
        pipeline = CpuPacketPipeline()
        print("Using: CpuPacketPipeline")

fn = Freenect2()
num_devices = fn.enumerateDevices()

if num_devices == 0:
    print("ERROR: No Kinect device connected!")
    sys.exit(1)

print(f"Found {num_devices} device(s)")
serial = fn.getDeviceSerialNumber(0)
device = fn.openDevice(serial, pipeline=pipeline)

# Setup frame listeners
types = FrameType.Color | FrameType.Ir | FrameType.Depth
listener = SyncMultiFrameListener(types)
device.setColorFrameListener(listener)
device.setIrAndDepthFrameListener(listener)

# Start device
device.start()
print("Kinect started")

# Initialize registration (for undistortion)
registration = Registration(device.getIrCameraParams(),
                          device.getColorCameraParams())

# Create frames for processing
undistorted = Frame(512, 424, 4)
registered = Frame(512, 424, 4)

# Get camera parameters
depth_params = device.getIrCameraParams()
CameraParams = {
    "cx": depth_params.cx,
    "cy": depth_params.cy,
    "fx": depth_params.fx,
    "fy": depth_params.fy,
}

print(f"Depth camera: fx={CameraParams['fx']:.2f}, fy={CameraParams['fy']:.2f}, "
      f"cx={CameraParams['cx']:.2f}, cy={CameraParams['cy']:.2f}")

def depthMatrixToPointCloudPos(z, scale=1000):
    """
    Convert depth matrix to 3D point cloud positions.
    Returns XYZ coordinates in meters.

    Based on colour_pc_viz.py algorithm.
    """
    # Create coordinate grids
    C, R = np.indices(z.shape)

    # Calculate X coordinates
    R = np.subtract(R, CameraParams['cx'])
    R = np.multiply(R, z)
    R = np.divide(R, CameraParams['fx'] * scale)

    # Calculate Y coordinates
    C = np.subtract(C, CameraParams['cy'])
    C = np.multiply(C, z)
    C = np.divide(C, CameraParams['fy'] * scale)

    # Return as (X, Y, Z) for TouchDesigner pointRender (RGB = XYZ)
    # Match colour_pc_viz.py: X=R, Y=-C (negated), Z=z
    return np.stack((R, -C, z / scale), axis=-1).astype(np.float32)

# Initialize Syphon servers
print("\nInitializing Syphon servers...")
print("  - KinectPointCloud (XYZ data)")
print("  - KinectRGB (color data)")

# Create Syphon servers
pointcloud_server = syphon.SyphonMetalServer("KinectPointCloud")
rgb_server = syphon.SyphonMetalServer("KinectRGB")

# Create textures (Syphon only supports 8-bit RGBA, so we'll encode float data)
# We'll scale XYZ coordinates to 0-255 range for transmission
pc_texture = create_mtl_texture(pointcloud_server.device, 512, 424)
rgb_texture = create_mtl_texture(rgb_server.device, 512, 424)

print("\nSyphon servers ready!")
print("\nIn TouchDesigner:")
print("1. Add Syphon In TOP → set server to 'KinectPointCloud'")
print("2. Add Syphon In TOP → set server to 'KinectRGB'")
print("3. Add pointRender from Palette")
print("4. Connect KinectPointCloud to pointRender input 1")
print("5. Connect KinectRGB to pointRender input 2")
print("6. Enable 'Set Vertex Colors' on pointRender")
print("\nPress Ctrl+C to stop")

frame_count = 0

try:
    while True:
        # Wait for new frames
        frames = listener.waitForNewFrame()
        color = frames["color"]
        depth = frames["depth"]

        # Apply registration (undistorts depth)
        registration.apply(color, depth, undistorted, registered)

        # Get undistorted depth as numpy array
        undistorted_data = undistorted.asarray(np.float32)

        # Calculate 3D point cloud
        points_xyz = depthMatrixToPointCloudPos(undistorted_data)

        # Create alpha channel (255 for valid points, 0 for invalid)
        valid_mask = (undistorted_data > 500) & (undistorted_data < 4500)
        alpha = (valid_mask * 255).astype(np.uint8)

        # Encode XYZ as 8-bit (scale from meters to 0-255 range)
        # points_xyz is already in (X, Y, Z) order from depthMatrixToPointCloudPos
        # X: -2 to +2 meters → 0 to 255
        # Y: -2 to +2 meters → 0 to 255
        # Z: 0.5 to 4.5 meters → 0 to 255
        xyz_scaled = np.zeros_like(points_xyz, dtype=np.float32)
        xyz_scaled[:, :, 0] = np.clip((points_xyz[:, :, 0] + 2.0) / 4.0 * 255, 0, 255)  # X → R
        xyz_scaled[:, :, 1] = np.clip((points_xyz[:, :, 1] + 2.0) / 4.0 * 255, 0, 255)  # Y → G
        xyz_scaled[:, :, 2] = np.clip((points_xyz[:, :, 2] - 0.5) / 4.0 * 255, 0, 255)  # Z → B

        # Combine into RGBA texture (uint8)
        pointcloud_data = np.dstack((xyz_scaled, alpha[:, :, np.newaxis]))
        pointcloud_data = np.ascontiguousarray(pointcloud_data, dtype=np.uint8)

        # Flip vertically (upside down fix)
        pointcloud_data = np.flipud(pointcloud_data)

        # Get registered RGB colors
        colors = registered.asarray(np.uint8)
        # Convert BGRA to RGBA
        colors = colors[:, :, [2, 1, 0, 3]]
        colors = np.ascontiguousarray(colors, dtype=np.uint8)

        # Flip vertically (upside down fix)
        colors = np.flipud(colors)

        # Copy data to Metal textures and publish
        copy_image_to_mtl_texture(pointcloud_data, pc_texture)
        pointcloud_server.publish_frame_texture(pc_texture)

        copy_image_to_mtl_texture(colors, rgb_texture)
        rgb_server.publish_frame_texture(rgb_texture)

        # Release frames
        listener.release(frames)

        frame_count += 1
        if frame_count % 30 == 0:
            print(f"Frames sent: {frame_count}")

except KeyboardInterrupt:
    print("\nStopping...")
finally:
    # Cleanup
    device.stop()
    device.close()
    print("Kinect closed")
    sys.exit(0)
