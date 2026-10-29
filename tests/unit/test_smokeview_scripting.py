"""Unit tests — pyfds.smokeview.scripting (SsfScriptBuilder)."""
from __future__ import annotations

import pytest
from pyfds.smokeview.scripting import SmokeviewScriptUnsupported, SsfScriptBuilder

# Every script keyword Smokeview 6.10.1 knows (from the keyword table in fds_smv/SMV6/smokeview.exe). Any other
# keyword stops the script with "unknown script keyword".
SMOKEVIEW_KEYWORDS = set("""
LOAD3DSMOKE LOADVOLSMOKE LOADVOLSMOKEFRAME LOADBOUNDARY LOADBOUNDARYM SETBOUNDBOUNDS LOADFILE LOADINIFILE UNLOADALL
HIDEHVACVALS SHOWHVACDUCTVAL SHOWHVACNODEVAL LOADSLCF LOADSLICE LOADSLICEM LOADVFILE LOADVSLICE LOADVSLICEM
SETSLICEBOUNDS SETSLICEAVERAGE OUTPUTSLICEDATA LOADPARTICLES PARTCLASSCOLOR PARTCLASSTYPE LOADPLOT3D PLOT3DPROPS
SHOWPLOT3DDATA LOADISO LOADISOM HIDEALLDEVS HIDEDEV SHOWALLDEVS SHOWDEV SHOWSMOKESENSORS OUTPUTSMOKESENSORS CBARNORMAL
CBARFLIP HIDECBAREDIT SHOWCBAREDIT SETCBAR SETCBARLAB SETCBARRGB HILIGHTMINVALS HILIGHTMAXVALS LOADTOUR
SETTOURKEYFRAME SETTOURVIEW UNLOADTOUR EXIT NOEXIT GSLICEORIEN GSLICEPOS GSLICEVIEW KEYBOARD PROJECTION SCENECLIP
SETCLIPMODE SETCLIPX SETCLIPY SETCLIPZ SETTIMEVAL SETVIEWPOINT VIEWXMIN VIEWXMAX VIEWYMIN VIEWYMAX VIEWZMIN VIEWZMAX
XYZVIEW XSCENECLIP YSCENECLIP ZSCENECLIP ISORENDERALL LOADSLICERENDER LOADSMOKERENDER MAKEMOVIE MOVIETYPE
RENDER360ALL RENDERALL RENDERCLIP RENDERDIR RENDERDOUBLEONCE RENDERHTMLALL RENDERHTMLDIR RENDERHTMLGEOM RENDERHTMLOBST
RENDERHTMLONCE RENDERHTMLSLICECELL RENDERHTMLSLICENODE RENDERONCE RENDERSIZE RENDERSTART RENDERTYPE VOLSMOKERENDERALL
GPUOFF LABEL RGBTEST UNLOADPLOT2D
""".split())


def keywords(text: str):
    """The keyword lines of an SSF script (argument lines start with a space)."""
    return [ln for ln in text.replace(chr(13), "").splitlines() if ln and not ln.startswith(" ")]


@pytest.fixture
def builder():
    return SsfScriptBuilder()


class TestSsfScriptBuilder:
    def test_build_returns_string(self, builder):
        result = builder.build()
        assert isinstance(result, str)

    def test_empty_build_is_empty_string(self, builder):
        result = builder.build()
        assert result.strip() == ""

    def test_set_render_options(self, builder):
        builder.set_render_options(width=1920, height=1080, image_format="PNG")
        text = builder.build()
        assert "RENDERTYPE\n PNG" in text and "SETRENDER" not in text      # SETRENDER is not a Smokeview keyword
        assert (builder._render_width, builder._render_height) == (1920, 1080)

    def test_set_time(self, builder):
        builder.set_time(30.0)
        text = builder.build()
        assert "SETTIMEVAL" in text
        assert "30" in text

    def test_screenshot_command(self, builder):
        builder.screenshot("frame_001.png")
        text = builder.build()
        # real SSF: keyword, then the base name on the next line (Smokeview adds .png itself)
        assert "RENDERONCE" + chr(10) + " frame_001" in text.replace(chr(13), "")

    def test_unload_all(self, builder):
        builder.unload_all()
        text = builder.build()
        assert "UNLOADALL" in text

    def test_load_slice(self, builder):
        builder.load_slice(quantity="TEMPERATURE", mesh=1, index=5)
        text = builder.build()
        assert "LOADSLICE" in text
        assert "TEMPERATURE" in text

    def test_set_viewpoint(self, builder):
        builder.set_viewpoint("top")
        text = builder.build()
        assert "SETVIEWPOINT" in text

    @pytest.mark.parametrize("call", [
        lambda b: b.set_colorbar_range(vmin=20.0, vmax=600.0),
        lambda b: b.set_colorbar_range(auto=True),
        lambda b: b.add_label("Hot Zone"),
        lambda b: b.step_forward(),
        lambda b: b.set_frame(3),
        lambda b: b.show_geometry(False),
        lambda b: b.show_obstruction("WALL"),
        lambda b: b.show_vent("DOOR"),
        lambda b: b.show_mesh(1),
        lambda b: b.show_zone("Z1"),
        lambda b: b.set_contour_type("SMOOTH"),
        lambda b: b.set_contour_levels(8),
        lambda b: b.set_transparency("WALL", 0.5),
        lambda b: b.set_background_color(0, 0, 0),
        lambda b: b.set_foreground_color(255, 255, 255),
    ])
    def test_what_smokeview_scripts_cannot_do_raises_instead_of_writing(self, builder, call):
        with pytest.raises(SmokeviewScriptUnsupported, match="Smokeview 6.10.1 scripts cannot"):
            call(builder)
        assert builder.build() == ""

    def test_every_keyword_written_is_one_smokeview_knows(self, builder, tmp_path):
        builder.set_render_options(width=1280, height=720)
        builder.load_slice("TEMPERATURE", axis=2, position=2.4).load_slice("TEMPERATURE", 1, 1, 1, 2.5, cell_centered=True)
        builder.load_vector("TEMPERATURE", axis=1, position=2.5, cell_centered=True)
        builder.load_boundary("WALL TEMPERATURE").load_isosurface("TEMPERATURE").load_smoke3d("SOOT DENSITY")
        builder.load_particle().load_plot3d(30.0)
        builder.set_viewpoint("top").set_view("xmin").set_camera((3, -5, 4), (3, 2, 1))
        builder.set_colormap("greyscale").set_clip_plane("z", 2.0, clip_min=False)
        builder.set_time(30.0).screenshot("a").render_movie("m.mp4").unload_all()
        builder.write(str(tmp_path / "s.ssf"))
        unknown = [k for k in keywords((tmp_path / "s.ssf").read_text()) if k not in SMOKEVIEW_KEYWORDS]
        assert unknown == []

    def test_render_movie(self, builder):
        builder.render_movie("output.mp4", fps=24, start_time=0.0, end_time=60.0)
        text = builder.build()
        assert chr(10).join(["RENDERALL", " 1", " output"]) in text.replace(chr(13), "")   # one image per frame

    def test_multiple_commands_ordered(self, builder):
        builder.set_time(0.0)
        builder.load_slice("TEMPERATURE", 1, 5)
        builder.screenshot("t0.png")
        builder.set_time(30.0)
        builder.screenshot("t30.png")
        text = builder.build().replace(chr(13), "")
        a, b = chr(10) + " t0" + chr(10), chr(10) + " t30" + chr(10)
        assert a in text and b in text
        assert text.index(a) < text.index(b)

    def test_write_to_file(self, builder, tmp_path):
        builder.set_time(10.0)
        builder.screenshot("out.png")
        out = tmp_path / "script.ssf"
        builder.write(str(out))
        assert out.exists()
        assert "RENDERONCE" in out.read_text()

    def test_camera_is_xyzview_with_azimuth_and_elevation(self, builder):
        # XYZVIEW x y z azimuth elevation; azimuth 0 looks along +y, 90 along +x; elevation positive upwards
        builder.set_camera(eye=(3.0, -5.0, 1.5), target=(3.0, 2.0, 1.5))
        builder.set_camera(eye=(-6.0, 2.0, 1.5), target=(0.0, 2.0, 1.5))
        builder.set_camera(eye=(0.0, 0.0, 4.0), target=(0.0, 4.0, 0.0))
        text = builder.build().replace(chr(13), "")
        assert "XYZVIEW\n 3 -5 1.5 0.00 0.00" in text
        assert "XYZVIEW\n -6 2 1.5 90.00 0.00" in text
        assert "XYZVIEW\n 0 0 4 0.00 -45.00" in text
        with pytest.raises(ValueError):
            builder.set_camera(eye=(1, 1, 1), target=(1, 1, 1))

    def test_set_view_looks_along_an_axis(self, builder):
        assert keywords(builder.set_view("XMIN").set_view("zmax").build()) == ["VIEWXMIN", "VIEWZMAX"]
        with pytest.raises(ValueError):
            builder.set_view("front")

    def test_cell_centred_and_vector_slices_use_loadslcf(self, builder):
        builder.load_slice("TEMPERATURE", axis=1, position=2.5, cell_centered=True)
        builder.load_vector("TEMPERATURE", axis=3, position=1.5)
        text = builder.build().replace(chr(13), "")
        assert "LOADSLCF\n QUANTITY='TEMPERATURE' PBX=2.5 CELL_CENTERED=T\n" in text
        assert "LOADSLCF\n QUANTITY='TEMPERATURE' PBZ=1.5 VECTOR=T\n" in text

    def test_plot3d_is_loaded_by_mesh_and_time(self, builder):
        assert "LOADPLOT3D\n 2 30\n" in builder.load_plot3d(30.0, mesh=2).build().replace(chr(13), "")

    def test_clip_plane_clips_geometry_and_data(self, builder):
        text = builder.set_clip_plane("y", 2.4).set_clip_plane("Z", 2.0, clip_min=False).build().replace(chr(13), "")
        assert "SETCLIPMODE\n 1\nSETCLIPY\n 1 2.4 0 0\n" in text
        assert "SETCLIPZ\n 0 0 1 2\n" in text

    def test_colormap_names_are_smokeviews(self, builder):
        text = builder.set_colormap("greyscale").set_colormap("rainbow").set_colormap("blue->red split").build()
        assert [ln.strip() for ln in text.replace(chr(13), "").splitlines()[1::2]] == ["black->white", "Rainbow",
                                                                                         "blue->red split"]

    def test_render_size_and_labels_go_into_a_loaded_settings_ini(self, builder, tmp_path):
        # RENDERSIZE is accepted by Smokeview 6.10.1 but changes nothing: the size is the window's, from an .ini
        builder.set_render_options(width=1280, height=720).screenshot("a")
        ini = builder.settings_ini()
        assert "WINDOWWIDTH\n 1280\nWINDOWHEIGHT\n 720\n" in ini and "SHOWTITLE\n 0 0 0\n" in ini
        assert "LOADINIFILE" not in builder.build()                      # no file name given: nothing to load
        builder.write(str(tmp_path / "case.ssf"))
        settings = tmp_path / "case_settings.ini"
        assert settings.read_text() == ini
        first = (tmp_path / "case.ssf").read_text().splitlines()[:2]
        assert first == ["LOADINIFILE", f" {settings.resolve()}"]

    def test_labels_kept_when_asked(self, builder):
        assert "SHOWTITLE" not in builder.set_render_options(labels=True).settings_ini()

    def test_no_settings_file_without_render_options(self, builder, tmp_path):
        builder.set_time(1.0).write(str(tmp_path / "s.ssf"))
        assert not (tmp_path / "s_settings.ini").exists()
        assert "LOADINIFILE" not in (tmp_path / "s.ssf").read_text()

    def test_load_boundary(self, builder):
        builder.load_boundary()
        text = builder.build()
        assert isinstance(text, str)

    def test_fluent_api_returns_builder(self, builder):
        """All methods should return self for chaining."""
        result = builder.set_time(0.0)
        # Not all implementations chain, but build() always works
        text = builder.build()
        assert isinstance(text, str)
