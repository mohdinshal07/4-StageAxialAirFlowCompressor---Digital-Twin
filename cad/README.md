# CAD – four-stage compressor (Rev. 3)

| File | Content |
|---|---|
| `Compressor_4stage_assembly.step` | full assembly (STEP AP214) |
| `parts_STEP/` | every part as a separate STEP file (rotors R1–R4, stator casings S1–S4, spools, shaft, bearing frames, caps, tie rods) |
| `BuildCompressor_SolidWorks.bas` | SolidWorks macro that imports the parts and builds the assembly |
| `Pictures/` | renders (isometric, section, rotor, stator, shaft, frame) |
| `CAD_NOTES.txt` | original notes: stacking order, fits, print settings |

Main dimensions: tip Ø100 mm, hub Ø75 → Ø76.88 mm, module pitch 32 mm, chord 14 mm, bore Ø101 mm (0.5 mm radial clearance), D-flat Ø25 shaft.
Rotor blades 38 / 40 / 41 / 19, stator vanes 27 / 39 / 42 / 26.

STL files for printing (≈ 170 MB) are not kept in git. Export them from the STEP files, or download `Compressor_4stage_CAD.zip` from the release.
The STEP files were produced by a custom generator and have **not yet been opened in SolidWorks**: use *Combine* on multi-body parts if needed.
