// Dashed edge program for Sigma v3 ("inbox" edges: delivered to the inbox,
// not pulled yet). The stock renderer has no dashed support, so this derives
// from EdgeRectangleProgram: the vertex shader forwards a_positionCoef (the
// 0..1 position along the edge) and the fragment shader discards fragments
// in a periodic pattern. Picking stays SOLID so clicking a dashed edge never
// falls through a gap. Composed with the stock arrow head for direction.

import {
  createEdgeCompoundProgram,
  EdgeArrowHeadProgram,
  EdgeRectangleProgram,
} from "sigma/rendering";

const VERTEX_SHADER_SOURCE = /* glsl */ `
attribute vec4 a_id;
attribute vec4 a_color;
attribute vec2 a_normal;
attribute float a_normalCoef;
attribute vec2 a_positionStart;
attribute vec2 a_positionEnd;
attribute float a_positionCoef;

uniform mat3 u_matrix;
uniform float u_sizeRatio;
uniform float u_zoomRatio;
uniform float u_pixelRatio;
uniform float u_correctionRatio;
uniform float u_minEdgeThickness;
uniform float u_feather;

varying vec4 v_color;
varying vec2 v_normal;
varying float v_thickness;
varying float v_feather;
varying float v_coef;

const float bias = 255.0 / 254.0;

void main() {
  float minThickness = u_minEdgeThickness;

  vec2 normal = a_normal * a_normalCoef;
  vec2 position = a_positionStart * (1.0 - a_positionCoef) + a_positionEnd * a_positionCoef;

  float normalLength = length(normal);
  vec2 unitNormal = normal / normalLength;

  float pixelsThickness = max(normalLength, minThickness * u_sizeRatio);
  float webGLThickness = pixelsThickness * u_correctionRatio / u_sizeRatio;

  gl_Position = vec4((u_matrix * vec3(position + unitNormal * webGLThickness, 1)).xy, 0, 1);

  v_thickness = webGLThickness / u_zoomRatio;
  v_normal = unitNormal;
  v_feather = u_feather * u_correctionRatio / u_zoomRatio / u_pixelRatio * 2.0;
  v_coef = a_positionCoef;

  #ifdef PICKING_MODE
  v_color = a_id;
  #else
  v_color = a_color;
  #endif

  v_color.a *= bias;
}
`;

const FRAGMENT_SHADER_SOURCE = /* glsl */ `
precision mediump float;

varying vec4 v_color;
varying vec2 v_normal;
varying float v_thickness;
varying float v_feather;
varying float v_coef;

const vec4 transparent = vec4(0.0, 0.0, 0.0, 0.0);

void main(void) {
  #ifdef PICKING_MODE
  // Picking stays solid: a click in a dash gap still hits the edge.
  gl_FragColor = v_color;
  #else
  // The dash pattern: ~14 dashes along the edge, 55% ink / 45% gap.
  if (fract(v_coef * 14.0) > 0.55) {
    gl_FragColor = transparent;
    return;
  }
  float dist = length(v_normal) * v_thickness;
  float t = smoothstep(v_thickness - v_feather, v_thickness, dist);
  gl_FragColor = mix(v_color, transparent, t);
  #endif
}
`;

class DashedEdgeRectangleProgram extends EdgeRectangleProgram {
  getDefinition() {
    return {
      ...super.getDefinition(),
      VERTEX_SHADER_SOURCE,
      FRAGMENT_SHADER_SOURCE,
    };
  }
}

export const DashedEdgeArrowProgram = createEdgeCompoundProgram([
  DashedEdgeRectangleProgram,
  EdgeArrowHeadProgram,
]);
