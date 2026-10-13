# Test map — which file covers which feature

Run everything: `python -X utf8 -m pytest tests -q --basetemp=/f/scratch/pt` (use `--basetemp` on F:, never under C:\Users).

| Step / rows | Feature | Test file |
|---|---|---|
| Whole product, real solver | Build a room fire, run the real FDS 6.10.1 through `api.execution.run`, read HRR and slice output, results scene, real Smokeview screenshots and movie frames (skipped when `fds_smv/` is missing) | `smoke/test_real_fds_smokeview.py` |
| Whole product | End-to-end smoke session (build, import, validate, export, save/load, scenarios, results scene, GUI opens) | `smoke/test_smoke_end_to_end.py` |
| G1 | Layer rules, size ratchet | `architecture/test_layer_rules.py` |
| G3 | Authoring API: species, zones, props, mults, moves, mesh transforms, texts | `unit/test_g3_authoring_api.py` |
| A1 | Typed OBST/MESH/PROP fields, SM3D, control functions, extras | `unit/test_a1_typed_fields.py` |
| A2 | Scenario run scripts, model-check sets, run gate, live checking | `unit/test_a2_scenario_and_checks.py` |
| B1 | Mesh operations (refine, split, merge, move, scale, mirror, rotate, zones, stretching, open boundaries) | `unit/test_b1_mesh_operations.py` |
| B2 | Walls, slabs, rooms, curved walls, stairs, roofs, trusses, booleans, blocks, particle cloud | `unit/test_b2_geometry_generators.py` |
| B3 | glTF/DAE/IFC import, BIM -> obstructions, repair, STL/OBJ export, plan backgrounds and tracing | `unit/test_b3_import_export.py` |
| P0: SRF-01, MAT-03, RXN-01, HVC-01, SIM-03 | Typed surfaces, liquid fuel, complex reactions, aircoil, gravity ramps, ambient | `unit/test_p0_physics_rows.py` |
| P0: LIB-01, MAT-05 | Libraries, import/export | `unit/test_p0_libraries.py` |
| P0: UX-03, UX-04, UX-08, FIO-01 | Clipboard, snapping, visibility, number format | `unit/test_p0_editing.py` |
| P0: IMP-02, RES-04 | OBJ/DXF import, slice display images | `unit/test_p0_import_and_slices.py` |
| C2 | Results scene, transfer functions, playback, camera path, probe, clip | `unit/test_c2_results_scene.py` |
| Parser/writer | Round trips, 900-file corpus | `integration/`, `unit/test_parser_regressions.py` |

Sample input files for these tests live in `fixtures/`:
`cube_unit.obj`, `pyramid_3dface.dxf`, `user_library_sample.json`, `slice_temperature_mesh1.sf`,
`complex_reaction_propane.fds` (plus the older `simple_room.fds`, `multi_mesh.fds`).

Real FDS and Smokeview are in `fds_smv/` (FDS 6.10.1, Smokeview 6). Not covered: ffmpeg movie encoding (ffmpeg is not installed here; the test checks the frames and the `127` result).
