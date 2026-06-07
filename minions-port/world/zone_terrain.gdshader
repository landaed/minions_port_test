shader_type spatial;
render_mode cull_disabled;

uniform sampler2D grass_tex : source_color, filter_linear, repeat_enable;
uniform sampler2D rock_tex : source_color, filter_linear, repeat_enable;
uniform sampler2D sand_tex : source_color, filter_linear, repeat_enable;
uniform float tex_scale = 0.12;
uniform float sand_height = 63.0;
uniform float sand_blend = 3.0;

varying vec3 wpos;
varying vec3 wnrm;

void vertex() {
	wpos = (MODEL_MATRIX * vec4(VERTEX, 1.0)).xyz;
	wnrm = normalize((MODEL_MATRIX * vec4(NORMAL, 0.0)).xyz);
}

vec3 tri(sampler2D t, vec3 p, vec3 n) {
	vec3 bw = pow(abs(n), vec3(4.0));
	bw /= (bw.x + bw.y + bw.z);
	return texture(t, p.zy * tex_scale).rgb * bw.x
		 + texture(t, p.xz * tex_scale).rgb * bw.y
		 + texture(t, p.xy * tex_scale).rgb * bw.z;
}

void fragment() {
	vec3 n = normalize(wnrm);
	float slope = clamp(n.y, 0.0, 1.0);
	vec3 g = tri(grass_tex, wpos, n);
	g = mix(g, vec3(0.26, 0.40, 0.14), 0.25);
	vec3 r = tri(rock_tex, wpos, n);
	vec3 s = tri(sand_tex, wpos, n);
	float rockw = smoothstep(0.55, 0.32, slope);
	float sandw = smoothstep(sand_height + sand_blend, sand_height, wpos.y);
	ALBEDO = mix(mix(g, s, sandw), r, rockw);
	ROUGHNESS = 0.96;
}
