/*
 * Debug X and Y Separately
 * =========================
 *
 * Shows X as RED, Y as GREEN to verify they're varying
 */

layout(location = 0) out vec4 fragColor;

void main()
{
    vec4 encoded = texture(sTD2DInputs[0], vUV.st);

    // Decode
    float x = (encoded.r * 4.0) - 2.0;   // -2 to +2
    float y = (encoded.g * 4.0) - 2.0;   // -2 to +2
    float z = (encoded.b * 4.0) + 0.5;   // 0.5 to 4.5

    // Normalize X and Y to 0-1 for visualization
    float x_vis = (x + 2.0) / 4.0;  // -2 to +2 → 0 to 1
    float y_vis = (y + 2.0) / 4.0;  // -2 to +2 → 0 to 1
    float z_vis = (z + 2.0) / 4.0;  // -2 to +2 → 0 to 1

    // Show X as RED, Y as GREEN
    // If working: should see color variation
    // If broken: will be one solid color
    fragColor = vec4(x_vis, y_vis, z_vis, encoded.a);
}
