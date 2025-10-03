/*
 * Point Cloud Decoder for TouchDesigner
 * ======================================
 *
 * Decodes 8-bit encoded XYZ coordinates back to float values.
 *
 * SETUP:
 * 1. Create GLSL TOP
 * 2. Set Output Resolution to 512x424
 * 3. Connect KinectPointCloud Syphon input
 * 4. Paste this shader into Pixel Shader
 * 5. Connect this GLSL TOP output to pointRender input 1
 */

layout(location = 0) out vec4 fragColor;

void main()
{
    // Sample the encoded point cloud data
    vec4 encoded = texture(sTD2DInputs[0], vUV.st);

    // Decode RGB back to XYZ coordinates (reverse the encoding)
    // Original encoding in Python:
    // X: (-2 to +2 meters) → (0 to 255)
    // Y: (-2 to +2 meters) → (0 to 255)
    // Z: (0.5 to 4.5 meters) → (0 to 255)

    // Decode with smaller scale for pointRender
    float x = ((encoded.r * 4.0) - 2.0) * 0.5;  // Scale down by 0.5
    float y = ((encoded.g * 4.0) - 2.0) * 0.5;  // Scale down by 0.5
    float z = ((encoded.b * 4.0) + 0.5) * 0.5;  // Scale down by 0.5

    // Alpha channel already has valid point mask
    float alpha = encoded.a;

    // Output as float RGBA (XYZ + alpha)
    // pointRender expects RGB = XYZ
    fragColor = vec4(x, y, z, alpha);
}
