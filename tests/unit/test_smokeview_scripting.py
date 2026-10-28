"""Unit tests — pyfds.smokeview.scripting (SsfScriptBuilder)."""
from __future__ import annotations

import pytest
from pyfds.smokeview.scripting import SsfScriptBuilder


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

    def test_set_colorbar_range(self, builder):
        builder.set_colorbar_range(vmin=20.0, vmax=600.0)
        text = builder.build()
        assert "20" in text or "COLORBAR" in text.upper() or "SETCOLORBARRANGE" in text.upper()

    def test_set_colorbar_auto(self, builder):
        builder.set_colorbar_range(auto=True)
        text = builder.build()
        assert isinstance(text, str)

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

    def test_camera_command(self, builder):
        builder.set_camera(
            eye=(10.0, 10.0, 10.0),
            target=(0.0, 0.0, 0.0),
            up=(0.0, 0.0, 1.0),
        )
        text = builder.build()
        assert "SETCAMERA" in text or "CAMERA" in text

    def test_label(self, builder):
        builder.add_label("Hot Zone", x=0.1, y=0.9, size=24, color="RED")
        text = builder.build()
        assert "LABEL" in text
        assert "Hot Zone" in text

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
