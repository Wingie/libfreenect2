# Point Cloud Visualization Explained

## Overview

The `colour_pc_viz.py` script creates a real-time 3D point cloud visualization of Kinect v2 data using PyQtGraph's OpenGL widget. It displays depth data as colored 3D points in space.

## How It Works

### 1. **Kinect Data Acquisition** (lines 17-43)
- Initializes Kinect device and starts streaming
- Listens for Color, IR, and Depth frames
- Creates registration object to align RGB and depth data

### 2. **Qt/OpenGL Visualization Setup** (lines 45-58)
- `GLViewWidget`: Main 3D viewport for rendering
- `GLGridItem`: Reference grid on the floor
- `GLScatterPlotItem`: Renders the point cloud

### 3. **Depth to 3D Conversion** (lines 73-94)
- **Camera Intrinsics** (lines 61-71): cx, cy, fx, fy parameters define the camera's optical properties
- **`depthMatrixToPointCloudPos()`**: Converts depth matrix to real-world XYZ coordinates using pinhole camera model:
  - `x = (pixel_x - cx) * depth / fx`
  - `y = (pixel_y - cy) * depth / fy`
  - `z = depth`

### 4. **Camera Orientation Compensation** (lines 96-156)
- **`CameraPosition`** dict (lines 97-104): Defines physical Kinect sensor position/rotation
  - `x, y, z`: Position in meters
  - `elevation`: Pitch angle (default -15°)
  - `azimuth`: Yaw angle
  - `roll`: Roll angle (disabled by default)
- **`applyCameraMatrixOrientation()`**: Rotates all points to compensate for sensor tilt

### 5. **Update Loop** (lines 159-246)
- Runs every 50ms (line 250)
- Gets frames from Kinect
- Applies color registration to map RGB to depth
- Converts depth to 3D points (Method 2, line 196 - fastest vectorized approach)
- Applies camera orientation
- Updates scatter plot with new positions and colors

## Changing Camera Controls

### **Interactive Camera Controls (Built-in)**

PyQtGraph's `GLViewWidget` has default mouse controls:

| Control | Action |
|---------|--------|
| **Left Mouse + Drag** | Rotate view around center |
| **Middle Mouse + Drag** | Pan view |
| **Right Mouse + Drag** | Zoom in/out |
| **Mouse Wheel** | Zoom in/out |

### **Programmatic Camera Control**

#### Option 1: Set Initial Camera Position

Add after line 48 (`gl_widget.show()`):

```python
gl_widget.setCameraPosition(distance=5, elevation=30, azimuth=45)
```

Parameters:
- `distance`: Camera distance from center (default ~10)
- `elevation`: Vertical angle in degrees
- `azimuth`: Horizontal rotation in degrees

#### Option 2: Manually Set Camera Options

```python
gl_widget.opts['distance'] = 5      # Zoom level
gl_widget.opts['elevation'] = 30    # Vertical angle
gl_widget.opts['azimuth'] = 45      # Horizontal angle
gl_widget.opts['center'] = QtGui.QVector3D(0, 0, 1)  # Look-at point
```

#### Option 3: Orbit Camera Animation

Add a camera animation by modifying the update function:

```python
# Add before update() function
camera_angle = 0

def update():
    global camera_angle
    colors = ((1.0, 1.0, 1.0, 1.0))

    # ... existing code ...

    # Rotate camera continuously
    camera_angle = (camera_angle + 1) % 360
    gl_widget.setCameraPosition(distance=5, elevation=30, azimuth=camera_angle)

    # ... rest of update code ...
```

#### Option 4: Keyboard Controls

Add keyboard handling after line 50:

```python
from PyQt5.QtCore import Qt

def keyPressEvent(event):
    if event.key() == Qt.Key_Up:
        gl_widget.opts['elevation'] += 5
    elif event.key() == Qt.Key_Down:
        gl_widget.opts['elevation'] -= 5
    elif event.key() == Qt.Key_Left:
        gl_widget.opts['azimuth'] -= 5
    elif event.key() == Qt.Key_Right:
        gl_widget.opts['azimuth'] += 5
    elif event.key() == Qt.Key_Plus:
        gl_widget.opts['distance'] -= 0.5
    elif event.key() == Qt.Key_Minus:
        gl_widget.opts['distance'] += 0.5

gl_widget.keyPressEvent = keyPressEvent
```

### **Adjusting Physical Kinect Orientation**

Modify `CameraPosition` dict (lines 97-104) to compensate for real-world sensor mounting:

```python
CameraPosition = {
    "x": 0,           # Sensor offset left/right (meters)
    "y": 0,           # Sensor offset forward/back (meters)
    "z": 1.7,         # Height from floor (meters)
    "roll": 0,        # Usually 0 unless sensor is tilted sideways
    "azimuth": 0,     # Rotation around vertical axis (degrees)
    "elevation": -15, # Downward tilt angle (degrees, negative = down)
}
```

### **Performance Tuning**

- **Update rate**: Change `t.start(50)` (line 250) - lower = faster updates
- **Vertex size**: Modify `v_rate` (line 181) to adjust point sizes
- **Processing method**: Lines 186-229 show 5 different methods - Method 2 is fastest

## Key Files Reference

- **Camera view settings**: `colour_pc_viz.py:182` (`gl_widget.opts['distance']`)
- **Initial viewport setup**: `colour_pc_viz.py:45-50`
- **Physical sensor position**: `colour_pc_viz.py:97-104`
- **Update frequency**: `colour_pc_viz.py:250`
