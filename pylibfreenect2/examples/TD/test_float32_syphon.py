#!/usr/bin/env python
"""
Test 32-bit Float Texture Support in syphon-python
===================================================
This script tests whether copy_image_to_mtl_texture() can handle
RGBA32Float textures, not just 8-bit RGBA8Unorm.
"""

import sys
import numpy as np

try:
    import syphon
    from syphon.utils.raw import create_mtl_texture
    from syphon.utils.numpy import copy_image_to_mtl_texture
except ImportError:
    print("ERROR: syphon-python not installed")
    sys.exit(1)

print("Testing 32-bit Float Texture Support")
print("=" * 50)

# Create a test server
server = syphon.SyphonMetalServer("Float32Test")
print(f"✓ Created Syphon server: {server}")

# Test 1: Create 8-bit texture (known to work)
print("\n[Test 1] Creating 8-bit RGBA texture (baseline)...")
try:
    texture_8bit = create_mtl_texture(server.device, 512, 424, pixel_format=70)
    print(f"✓ 8-bit texture created: {texture_8bit}")

    # Create test data (8-bit)
    test_data_8bit = np.random.randint(0, 255, (424, 512, 4), dtype=np.uint8)
    copy_image_to_mtl_texture(test_data_8bit, texture_8bit)
    print("✓ Successfully copied uint8 data to 8-bit texture")
except Exception as e:
    print(f"✗ 8-bit test FAILED: {e}")
    sys.exit(1)

# Test 2: Create 32-bit float texture
print("\n[Test 2] Creating 32-bit float RGBA texture...")
try:
    texture_32float = create_mtl_texture(server.device, 512, 424, pixel_format=115)
    print(f"✓ 32-bit float texture created: {texture_32float}")
except Exception as e:
    print(f"✗ Could not create 32-bit float texture: {e}")
    sys.exit(1)

# Test 3: Try to copy float32 data to float texture
print("\n[Test 3] Copying float32 numpy array to 32-bit float texture...")
try:
    # Create test data (float32) - simulating XYZ coordinates + alpha
    test_data_float = np.random.uniform(-2.0, 2.0, (424, 512, 4)).astype(np.float32)
    copy_image_to_mtl_texture(test_data_float, texture_32float)
    print("✓ SUCCESS! float32 data copied to 32-bit float texture")
    print("\n" + "=" * 50)
    print("RESULT: syphon-python DOES support 32-bit float textures!")
    print("=" * 50)
    print("\nYou can now modify kinect_syphon_sender.py to use:")
    print("  - pixel_format=115 (RGBA32Float)")
    print("  - Send raw float32 XYZ data without encoding")
    print("  - Remove normalization to 0-255 range")
    sys.exit(0)
except Exception as e:
    print(f"✗ FAILED to copy float32 data: {e}")
    print("\n" + "=" * 50)
    print("RESULT: syphon-python does NOT support 32-bit float texture copying")
    print("=" * 50)
    print("\nStick with current 8-bit encoding approach.")
    print("Limitation is in copy_image_to_mtl_texture(), not create_mtl_texture().")
    sys.exit(1)
