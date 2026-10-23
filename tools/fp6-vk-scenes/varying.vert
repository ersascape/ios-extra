#version 450
layout(location = 0) out vec4 c;
void main()
{
	vec2 p[3] = vec2[](vec2(-0.5, -0.5), vec2(0.5, -0.5), vec2(0.0, 0.5));
	vec4 cols[3] = vec4[](vec4(1, 0, 0, 1), vec4(0, 1, 0, 1), vec4(0, 0, 1, 1));
	c = cols[gl_VertexIndex];
	gl_Position = vec4(p[gl_VertexIndex], 0.0, 1.0);
}
