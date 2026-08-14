varying vec3 vNormal;

void main(){

    float intensity = pow(
        0.72 -
        dot(vNormal,vec3(0.0,0.0,1.0)),
        5.0
    );

    vec3 atmosphereColor = vec3(
        0.33,
        0.76,
        1.0
    );

    gl_FragColor =
        vec4(
            atmosphereColor,
            intensity
        );

}
