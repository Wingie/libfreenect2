# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

libfreenect2 is a driver for Kinect for Windows v2 (K4W2) devices that provides RGB image transfer, IR and depth image transfer, and registration of RGB and depth images. It's a C++ library with Python bindings that supports multiple hardware-accelerated depth processing pipelines.

## Build System and Commands

### Initial Setup
```bash
# Install dependencies (macOS)
brew update
brew install libusb glfw3 jpeg-turbo

# Download source and create build directory
mkdir build && cd build
```

### Build Commands
```bash
# Standard build
cmake ..
make

# Build with specific options
cmake .. -DCMAKE_INSTALL_PREFIX=$HOME/freenect2
make
make install

# Windows build
cmake .. -G "Visual Studio 16 2019"
cmake --build . --config RelWithDebInfo --target install
```

### Running and Testing
```bash
# Run the main test program
./bin/Protonect

# For installed version
$HOME/freenect2/bin/Protonect

# Test with specific pipeline (cl, cuda, opengl)
LIBFREENECT2_PIPELINE=cl ./bin/Protonect
```

### CMake Options
Key configuration options:
- `ENABLE_OPENGL=ON/OFF` - OpenGL depth processing support
- `ENABLE_OPENCL=ON/OFF` - OpenCL depth processing support
- `ENABLE_CUDA=ON/OFF` - CUDA depth processing support
- `BUILD_EXAMPLES=ON/OFF` - Build example programs
- `BUILD_OPENNI2_DRIVER=ON/OFF` - Build OpenNI2 driver

## Code Architecture

### Core Components

**Device Management (`libfreenect2.cpp`, `include/libfreenect2/libfreenect2.hpp`)**
- `Freenect2` - Main library context and device discovery
- `Freenect2Device` - Individual device control and data streaming

**Data Processing Pipeline (`packet_pipeline.h`)**
- CPU pipeline: Basic CPU-based depth processing
- OpenGL pipeline: GPU-accelerated using OpenGL shaders
- OpenCL pipeline: GPU-accelerated using OpenCL kernels
- CUDA pipeline: GPU-accelerated using CUDA

**Frame Handling (`frame_listener.hpp`, `frame_listener_impl.h`)**
- `FrameListener` - Interface for receiving processed frames
- Frame types: RGB, IR, Depth, with registration support

**Registration (`registration.h`)**
- RGB-Depth alignment and coordinate transformation
- Distortion correction and camera calibration parameters

### Key Directories

- `src/` - Core library implementation
- `include/libfreenect2/` - Public API headers
- `include/internal/` - Internal implementation headers
- `examples/` - Example applications (Protonect viewer)
- `pylibfreenect2/` - Python bindings
- `src/openni2/` - OpenNI2 driver implementation

### Processing Pipelines

The library supports multiple depth processing backends:

1. **CPU Pipeline** (`cpu_depth_packet_processor.cpp`) - Basic fallback
2. **OpenGL Pipeline** (`opengl_depth_packet_processor.cpp`) - Uses shaders in `src/shader/`
3. **OpenCL Pipeline** (`opencl_depth_packet_processor.cpp`) - Uses kernels in `.cl` files
4. **CUDA Pipeline** (`cuda_depth_packet_processor.cu`) - CUDA implementation

### USB Communication

- `src/usb_control.cpp` - Low-level USB protocol implementation
- `src/event_loop.cpp` - USB event handling and transfer management
- `src/transfer_pool.cpp` - USB transfer buffer management

## Platform-Specific Notes

### Linux
- Requires udev rules: `sudo cp platform/linux/udev/90-kinect2.rules /etc/udev/rules.d/`
- USB 3.0 controller required (Intel/NEC work best)

### macOS
- VideoToolbox JPEG decoding support available
- Use homebrew for dependencies

### Windows
- Requires UsbDk or libusbK driver installation
- Visual Studio 2015+ supported
- TurboJPEG required for RGB processing

## Python Bindings

Located in `pylibfreenect2/` directory:
```bash
cd pylibfreenect2
python setup.py install
```

## Testing Hardware

The library requires:
- USB 3.0 controller (NEC or Intel chipsets recommended)
- Kinect for Windows v2 sensor
- Adequate power supply for the sensor

Use `LIBUSB_DEBUG=3` environment variable for USB debugging.