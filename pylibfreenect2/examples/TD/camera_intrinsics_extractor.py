#!/usr/bin/env python
"""
Kinect v2 Camera Intrinsics Extractor
======================================

This script extracts the camera intrinsic parameters from your Kinect v2 sensor.
These parameters are needed for the GLSL shaders in TouchDesigner to properly
align RGB colors with the depth point cloud.

Usage:
    python camera_intrinsics_extractor.py

The script will print the parameters and save them to 'camera_params.txt'
"""

import sys
import os
from pylibfreenect2 import Freenect2, SyncMultiFrameListener
from pylibfreenect2 import FrameType

print("="*60)
print("Kinect v2 Camera Intrinsics Extractor")
print("="*60)
print()

# Initialize Kinect
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

print()

fn = Freenect2()
num_devices = fn.enumerateDevices()

if num_devices == 0:
    print("ERROR: No Kinect device connected!")
    sys.exit(1)

print(f"Found {num_devices} device(s)")
serial = fn.getDeviceSerialNumber(0)
print(f"Device serial: {serial}")
print()

# Open device
device = fn.openDevice(serial, pipeline=pipeline)

# Need to start device to get proper camera parameters
types = FrameType.Color | FrameType.Depth
listener = SyncMultiFrameListener(types)
device.setColorFrameListener(listener)
device.setIrAndDepthFrameListener(listener)
device.start()

# Now get camera parameters (after device started)
depth_params = device.getIrCameraParams()
color_params = device.getColorCameraParams()

print("="*60)
print("DEPTH CAMERA PARAMETERS (IR Camera)")
print("="*60)
print(f"fx (Focal length X): {depth_params.fx}")
print(f"fy (Focal length Y): {depth_params.fy}")
print(f"cx (Principal point X): {depth_params.cx}")
print(f"cy (Principal point Y): {depth_params.cy}")
print(f"k1 (Radial distortion): {depth_params.k1}")
print(f"k2 (Radial distortion): {depth_params.k2}")
print(f"k3 (Radial distortion): {depth_params.k3}")
print(f"p1 (Tangential distortion): {depth_params.p1}")
print(f"p2 (Tangential distortion): {depth_params.p2}")
print()

print("="*60)
print("COLOR CAMERA PARAMETERS (RGB Camera)")
print("="*60)
print(f"fx (Focal length X): {color_params.fx}")
print(f"fy (Focal length Y): {color_params.fy}")
print(f"cx (Principal point X): {color_params.cx}")
print(f"cy (Principal point Y): {color_params.cy}")
# Note: ColorCameraParams doesn't have distortion coefficients in pylibfreenect2
print("(Color camera distortion params not available in this API)")
print()

# Save to file in the same directory as this script
script_dir = os.path.dirname(os.path.abspath(__file__))
output_file = os.path.join(script_dir, "camera_params.txt")
print(f"Saving to: {output_file}")
with open(output_file, 'w') as f:
    f.write("KINECT V2 CAMERA PARAMETERS\n")
    f.write("="*60 + "\n\n")

    f.write("DEPTH CAMERA (IR):\n")
    f.write(f"fx = {depth_params.fx}\n")
    f.write(f"fy = {depth_params.fy}\n")
    f.write(f"cx = {depth_params.cx}\n")
    f.write(f"cy = {depth_params.cy}\n")
    f.write(f"k1 = {depth_params.k1}\n")
    f.write(f"k2 = {depth_params.k2}\n")
    f.write(f"k3 = {depth_params.k3}\n")
    f.write(f"p1 = {depth_params.p1}\n")
    f.write(f"p2 = {depth_params.p2}\n\n")

    f.write("COLOR CAMERA (RGB):\n")
    f.write(f"fx = {color_params.fx}\n")
    f.write(f"fy = {color_params.fy}\n")
    f.write(f"cx = {color_params.cx}\n")
    f.write(f"cy = {color_params.cy}\n")
    f.write("(Distortion coefficients not available for color camera)\n\n")

    f.write("\nFOR TOUCHDESIGNER GLSL SHADER:\n")
    f.write("="*60 + "\n")
    f.write("Copy these values into your GLSL MAT uniforms:\n\n")
    f.write(f"uniform float depthFx = {depth_params.fx};\n")
    f.write(f"uniform float depthFy = {depth_params.fy};\n")
    f.write(f"uniform float depthCx = {depth_params.cx};\n")
    f.write(f"uniform float depthCy = {depth_params.cy};\n\n")
    f.write(f"uniform float colorFx = {color_params.fx};\n")
    f.write(f"uniform float colorFy = {color_params.fy};\n")
    f.write(f"uniform float colorCx = {color_params.cx};\n")
    f.write(f"uniform float colorCy = {color_params.cy};\n")

print(f"Parameters saved to: {output_file}")
print()
print("="*60)
print("NEXT STEPS:")
print("="*60)
print("1. Open the GLSL MAT in TouchDesigner")
print("2. Add the uniform parameters shown above")
print("3. Copy the shader code from rgb_alignment_shader.glsl")
print("4. Connect your Syphon inputs")
print("5. See point_cloud_setup.txt for full instructions")
print("="*60)

# Stop and close device
device.stop()
device.close()
print("\nDone!")
