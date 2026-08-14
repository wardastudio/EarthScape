function smoothstep(a,b,x){
    const t = Math.min(Math.max((x-a)/(b-a),0),1);
    return t*t*(3-2*t);
}

function easeOutCubic(t){
    return 1-Math.pow(1-t,3);
}

function easeInOutCubic(t){
    return t<0.5
        ?4*t*t*t
        :1-Math.pow(-2*t+2,3)/2;
}

function bump(p,a,b,c,d){
    const rise = smoothstep(a,b,p);
    const fall = c===undefined
        ?0
        :smoothstep(c,d,p);
    return rise*(1-fall);
}
