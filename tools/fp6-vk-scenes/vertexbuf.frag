#version 450
layout(location = 0) in vec3 c;
layout(location = 0) out vec4 color;
void main() { color = vec4(c, 1.0); }
