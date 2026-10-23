#version 450
layout(location = 0) flat out vec4 c;
void main()
{
	/* Triangle 0 is near (z 0.2, red); triangle 1 is far (z 0.8, green) and overlaps it,
	 * so with depth test LESS the green one must not cover the red one. */
	vec2 p[6] = vec2[](vec2(-0.7, -0.7), vec2(0.5, -0.7), vec2(-0.1, 0.6),
	                   vec2(-0.5, -0.5), vec2(0.7, -0.5), vec2(0.1, 0.8));
	float z[6] = float[](0.2, 0.2, 0.2, 0.8, 0.8, 0.8);
	c = gl_VertexIndex < 3 ? vec4(1, 0, 0, 1) : vec4(0, 1, 0, 1);
	gl_Position = vec4(p[gl_VertexIndex], z[gl_VertexIndex], 1.0);
}
