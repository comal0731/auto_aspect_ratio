import { app } from "../../scripts/app.js";

app.registerExtension({
    name: "Comal.CompactNodes",
    async beforeRegisterNodeDef(nodeType, nodeData, app) {
        if (nodeData.name === "AutoAspectPad" || nodeData.name === "AutoAspectUnpad") {
            const origComputeSize = nodeType.prototype.computeSize;
            nodeType.prototype.computeSize = function (out) {
                const size = origComputeSize ? origComputeSize.call(this, out) : [180, 60];
                size[0] = Math.max(140, size[0] * 0.55); // 최소 가로폭 축소, 필요하면 140 값 조정
                return size;
            };

            const onNodeCreated = nodeType.prototype.onNodeCreated;
            nodeType.prototype.onNodeCreated = function () {
                const r = onNodeCreated ? onNodeCreated.apply(this, arguments) : undefined;
                this.setSize(this.computeSize());
                return r;
            };
        }
    },
});
