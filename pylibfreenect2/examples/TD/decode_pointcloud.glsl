/*
 * Point Cloud Decoder for TouchDesigner
 * ======================================
 *
 * Decodes 8-bit encoded XYZ coordinates back to float values.
 * Based on scientific analysis of colour_pc_viz.py
 *
 * SETUP:
 * 1. Create GLSL TOP in TouchDesigner
 * 2. Set Output Resolution to 512x424
 * 3. Connect KinectPointCloud Syphon input to this GLSL TOP
 * 4. Paste this shader into Pixel Shader field
 * 5. Connect this GLSL TOP output to pointRender input 1
 */

layout(location = 0) out vec4 fragColor;

void main()
{
    // Sample the encoded point cloud data from Syphon
    vec4 encoded = texture(sTD2DInputs[0], vUV.st);

    // Decode RGB back to XYZ coordinates (exact reverse of Python encoding)
    // Python encoding in kinect_syphon_sender.py:
    // R channel: X from -2 to +2 meters → 0 to 1
    // G channel: Y from -2 to +2 meters → 0 to 1
    // B channel: Z from 0.5 to 4.5 meters → 0 to 1

    // Decode back to meters (exact reversal)
    float x = (encoded.r * 4.0) - 2.0;   // 0-1 → -2 to +2 meters
    float y = (encoded.g * 4.0) - 2.0;   // 0-1 → -2 to +2 meters
    float z = (encoded.b * 4.0) + 0.5;   // 0-1 → 0.5 to 4.5 meters

    // Alpha channel has valid point mask
    // White (1.0) = valid point, Black (0.0) = invalid/no data
    float alpha = encoded.a;

    // Output as RGBA where RGB = XYZ (pointRender expects R=X, G=Y, B=Z)
    fragColor = vec4(x, y, z, alpha);
}
