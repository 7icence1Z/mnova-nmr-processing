// Include this helper in the sample-specific .qs before invoking it.
// Apply AFTER analysis objects and each Expansion are created, before saving.
function applyCourseDisplayStyle(spec, isExpansion) {
    if (!spec.isValid()) throw new Error("Invalid NMR spectrum for display style");
    var style = {
        "background.color": "#ffffff",
        "background.opacity": 100,
        "grid.showhorizontal": false,
        "grid.showvertical": false,
        "grid.showdiagonal": false,
        "grid.showframe": Boolean(isExpansion),
        "axes.vertical.visible": false,
        "axes.vertical.showlabel": false,
        "axes.horizontal.visible": true,
        "multiplets.show": false,
        "multiplets.integral.curve.show": false,
        "multiplets.integral.label.show": false,
        "multiplets.integral.methodlabel.show": false,
        "integrals.show": true,
        "integrals.curve.show": true,
        "integrals.curve.color": "#008000",
        "integrals.label.show": true,
        "integrals.label.position": "Segment",
        "integrals.label.color": "#0000ff",
        "peaks.show": true,
        "peaks.color": "#0000ff"
    };
    for (var key in style) {
        spec.setProperty(key, style[key]);
        // Fail explicitly if the current version cannot retain a visibility flag.
        var actual = spec.getProperty(key);
        // Some versions return grid.showframe as the string "true"/"false".
        if (actual === "true") actual = true;
        if (actual === "false") actual = false;
        if (typeof style[key] === "boolean" && actual !== style[key]) {
            throw new Error("Display property was not retained: " + key);
        }
    }
    spec.update();
}
