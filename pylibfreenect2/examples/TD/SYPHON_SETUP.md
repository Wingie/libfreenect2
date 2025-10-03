# Kinect v2 → TouchDesigner via Syphon

This method sends properly aligned point cloud data from Python to TouchDesigner using Syphon.

## Why This Works

- Uses libfreenect2's `registration.apply()` for proper undistortion (like your working colour_pc_viz.py)
- Sends XYZ point cloud as 32-bit float texture via Syphon
- TouchDesigner's `pointRender` handles the 3D rendering
- Fast (GPU shared memory) and accurate

## Setup

### 1. Install Python Dependencies

```bash
pip install syphon-python numpy
```

### 2. Run the Sender Script

```bash
cd /Users/wingston/code/libfreenect2/pylibfreenect2/examples/TD
python kinect_syphon_sender.py
```

You should see:
```
Syphon servers ready!

In TouchDesigner:
1. Add Syphon In TOP → set server to 'KinectPointCloud'
2. Add Syphon In TOP → set server to 'KinectRGB'
...
```

### 3. TouchDesigner Setup

1. **Add Syphon In TOP #1**
   - Drag `Syphon Spout In TOP` into your network
   - Parameters → **Server Name**: `KinectPointCloud`
   - This receives XYZ point positions

2. **Add Syphon In TOP #2**
   - Drag another `Syphon Spout In TOP`
   - Parameters → **Server Name**: `KinectRGB`
   - This receives RGB colors

3. **Add pointRender Component**
   - Open Palette (View → Palette Browser)
   - Search for `pointRender`
   - Drag into network

4. **Connect Everything**
   - Connect `KinectPointCloud` Syphon → `pointRender` input 1
   - Connect `KinectRGB` Syphon → `pointRender` input 2

5. **Configure pointRender**
   - Click on pointRender
   - Parameters → **Set Vertex Colors** = ON
   - **Point Size** = 2-5 (adjust to taste)
   - **Resolution** = 1280x720 (or desired output size)

6. **View the Result**
   - Click on pointRender to see the 3D point cloud
   - Drag in the viewer to rotate camera
   - Should look like your colour_pc_viz.py but in TouchDesigner!

## Troubleshooting

**"No Syphon servers found"**
- Make sure Python script is running
- Check console for errors

**"Point cloud looks weird"**
- Make sure you connected KinectPointCloud (not KinectRGB) to input 1
- Check "Set Vertex Colors" is enabled

**"Script fails to import syphon-python"**
```bash
pip install syphon-python
```

**"Colors don't match"**
- This uses libfreenect2's registration, so colors should be properly aligned
- If still off, check the Python script is using `registered` colors

## Performance

- Should run at ~30 FPS
- Uses GPU shared memory (fast)
- XYZ data is 32-bit float for accuracy

## Next Steps

Once working, you can:
- Add effects in TouchDesigner
- Connect to Ableton Live via MIDI/OSC for music control
- Use CHOP Executes to trigger events based on hand position
- Add particle systems, shaders, etc.

Enjoy!
