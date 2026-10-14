/**
 * Sample reversed logic file.
 * Replace with your extracted web/mobile JS encoding logic.
 */
function calculateSignature(params, timestamp) {
    // Demo hash/signature routine
    var payload = params + ":" + timestamp;
    var hash = 0;
    for (var i = 0; i < payload.length; i++) {
        var char = payload.charCodeAt(i);
        hash = ((hash << 5) - hash) + char;
        hash |= 0;
    }
    return "sig_" + Math.abs(hash).toString(16);
}

globalThis.calculateSignature = calculateSignature;
