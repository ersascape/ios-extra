# AdrenoGPU PM4 builder

`Fp6A8xxRegs.h` is generated: the A8XX view of Mesa's freedreno register database (pinned Mesa
`6a7d3020a781`, the tree our Turnip captures come from), written by `tools/gen-a8xx-regs.py`.

    python3 tools/gen-a8xx-regs.py --mesa <mesa checkout> --out drivers/adrenogpu/pm4/Fp6A8xxRegs.h

The generator is the MIT-licensed `tools/gen-a8xx-regs.py` of the Snapintosh project, copied unchanged
(upstream `2c60b47`); the header keeps Mesa's own licence notice. Regenerating must give byte-identical output.

The builder checks its streams against Turnip's with `tools/fp6-pm4-state.py`, which walks a capture
(following indirect buffers and draw-state groups) and returns the register state at the draw.
Rule learned on the phone (see `NOTES.md`, 2026-10-24): between a render-pass clear and the first
draw the stream needs a cache flush, otherwise sampled textures come out wrong on this part.
