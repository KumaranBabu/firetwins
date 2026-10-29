"""Unit tests — pyfds.smokeview.ini_writer (SmvIniConfig, SmvIniWriter, SmvIniParser).

The expected text is Smokeview 6.10.1's own .ini format (keyword alone on a line, values on the next line indented
by one space), as written by ``smokeview -ini``. Each keyword was checked by rendering the demo cases.
"""
from __future__ import annotations

import pytest
from pyfds.smokeview.ini_writer import (
    SmvIniConfig, SmvIniParser, SmvIniUnsupported, SmvIniWriter,
)
from pyfds.smokeview.scripting_common import SmokeviewScriptUnsupported

# Keywords Smokeview 6.10.1 reads from an .ini file and that changed a render when tested.
VERIFIED_KEYWORDS = {
    "FLIP", "BACKGROUNDCOLOR", "FOREGROUNDCOLOR", "SHOWFRAME", "SHOWOTHERVENTS", "SHOWOPENVENTS", "LIGHTPROP",
    "SHOWTIMEBAR", "SHOWTIMELABEL", "SHOWCOLORBARS", "SHOWTITLE", "WINDOWWIDTH", "WINDOWHEIGHT", "RENDERFILETYPE",
    "COLORBARTYPE", "V2_SLICE",
}


def full_config() -> SmvIniConfig:
    cfg = SmvIniConfig(
        background_color=(0, 0, 0), foreground_color=(255, 255, 255), show_frame=False, show_vents=False,
        show_open_vents=True, ambient_light=0.2, diffuse_light=0.4, show_time=False, show_colorbar=True,
        show_title=False, window_width=1280, window_height=720, render_format="jpg", colormap="blue->red split",
    )
    cfg.add_colorbar("temp", vmin=20, vmax=300)
    cfg.add_colorbar("VIS_C", auto_range=True)
    return cfg


def keywords(text: str):
    return [ln for ln in text.splitlines() if ln and not ln.startswith(" ")]


class TestWriter:
    def test_empty_config_writes_nothing(self):
        assert SmvIniWriter().generate(SmvIniConfig()) == ""

    def test_keyword_then_indented_value_line(self):
        text = SmvIniWriter().generate(SmvIniConfig(window_width=1280, window_height=720))
        assert text == "WINDOWWIDTH\n 1280\nWINDOWHEIGHT\n 720\n"

    def test_no_invented_key_value_syntax(self):
        text = SmvIniWriter().generate(full_config())
        assert "=" not in text and "[" not in text

    def test_every_keyword_written_was_verified(self):
        assert set(keywords(SmvIniWriter().generate(full_config()))) <= VERIFIED_KEYWORDS

    def test_every_value_line_is_indented(self):
        lines = SmvIniWriter().generate(full_config()).splitlines()
        values = [ln for ln in lines if ln not in VERIFIED_KEYWORDS]
        assert values and all(ln.startswith(" ") and not ln.startswith("  ") for ln in values)

    def test_colours_are_0_to_1_and_flip_off(self):
        text = SmvIniWriter().generate(SmvIniConfig(background_color=(255, 0, 0)))
        assert text == "FLIP\n 0\nBACKGROUNDCOLOR\n 1.000000 0.000000 0.000000\n"

    def test_bad_colour_rejected(self):
        with pytest.raises(ValueError):
            SmvIniWriter().generate(SmvIniConfig(background_color=(300, 0, 0)))

    def test_slice_bounds_set_and_auto(self):
        cfg = SmvIniConfig().add_colorbar("temp", vmin=20, vmax=300).add_colorbar("VIS_C", auto_range=True)
        text = SmvIniWriter().generate(cfg)
        assert "V2_SLICE\n 0 20.000000 0 300.000000 temp\n" in text       # 0 = use the given bound
        assert "V2_SLICE\n 1 0.000000 1 100.000000 VIS_C\n" in text       # 1 = bounds of the loaded data

    def test_quantity_must_be_short_name(self):
        with pytest.raises(ValueError):
            SmvIniConfig().add_colorbar("SOOT VISIBILITY")

    def test_labels_and_lighting(self):
        cfg = SmvIniConfig(show_title=True, show_time=False, show_colorbar=False, ambient_light=0.1)
        text = SmvIniWriter().generate(cfg)
        assert "SHOWTITLE\n 1 0 1\n" in text
        assert "SHOWTIMEBAR\n 0 2\nSHOWTIMELABEL\n 0\n" in text
        assert "SHOWCOLORBARS\n 0 0\n" in text
        assert "LIGHTPROP\n 0.100000 0.100000 0.100000\n 0.500000 0.500000 0.500000\n" in text

    def test_render_format(self):
        assert "RENDERFILETYPE\n 1 0 2\n" in SmvIniWriter().generate(SmvIniConfig(render_format="JPEG"))
        with pytest.raises(ValueError):
            SmvIniWriter().generate(SmvIniConfig(render_format="bmp"))

    def test_write_file(self, tmp_path):
        out = tmp_path / "case.ini"
        SmvIniWriter().write(full_config(), str(out))
        assert out.read_text(encoding="utf-8").startswith("FLIP\n 0\n")


class TestUnsupported:
    @pytest.mark.parametrize("name", [
        "show_geometry", "show_obstructions", "transparency_mode", "show_mesh_boundaries", "render_width",
        "animation_fps", "smoke3d_opacity_cutoff", "smoke3d_max_opacity",
    ])
    def test_removed_setting_raises(self, name):
        cfg = SmvIniConfig()
        with pytest.raises(SmvIniUnsupported, match="Smokeview 6.10.1"):
            setattr(cfg, name, 1)
        with pytest.raises(SmvIniUnsupported):
            getattr(cfg, name)

    def test_viewpoints_and_surface_colours_raise(self):
        with pytest.raises(SmvIniUnsupported):
            SmvIniConfig().add_viewpoint("Front", eye=(1, 0, 0), target=(0, 0, 0))
        with pytest.raises(SmvIniUnsupported):
            SmvIniConfig().add_surface_color("FIRE", rgb=(255, 0, 0))

    def test_is_a_script_unsupported(self):
        assert issubclass(SmvIniUnsupported, SmokeviewScriptUnsupported)

    def test_unknown_attribute_is_attribute_error(self):
        with pytest.raises(AttributeError):
            SmvIniConfig().nonsense


class TestParser:
    def test_round_trip(self):
        cfg = full_config()
        back = SmvIniParser().parse_string(SmvIniWriter().generate(cfg))
        assert back == cfg

    def test_parse_file(self, tmp_path):
        p = tmp_path / "x.ini"
        SmvIniWriter().write(full_config(), str(p))
        assert SmvIniParser().parse(str(p)) == full_config()

    def test_missing_file(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            SmvIniParser().parse(str(tmp_path / "none.ini"))

    def test_reads_smokeview_dump(self):
        # Excerpt of what `smokeview -ini` writes (Smokeview 6.10.1), including lines Smokeview writes unindented.
        text = (
            "# NIST Smokeview configuration file, Release Apr  4 2025\n\n"
            " ------------ global ini settings ------------\n\n"
            "BACKGROUNDCOLOR\n 0.000000 0.000000 0.000000\n"
            "COLORBAR_FLIP\n 0 1\n"
            "FLIP\n 1\n"
            "FOREGROUNDCOLOR\n 1.000000 1.000000 1.000000\n"
            "LIGHTPROP\n 0.600000 0.600000 0.600000\n 0.500000 0.500000 0.500000\n"
            "WINDOWWIDTH\n 640\nWINDOWHEIGHT\n 480\n"
            "FIREPARAMS\n"
            "SHOWFRAME\n 1\nSHOWFRAMELABEL\n 1\n"
            "SHOWSKYSPHERE\n0 1 1 0 1 4.000000\n"
            "SHOWTITLE\n 1 0 0\n"
            "SHOWCOLORBARS\n 1 0\n"
            "RENDERFILETYPE\n 0 0 2\n"
            "COLORBARTYPE\n 0 % (null) \n"
            "V2_SLICE\n 1 20.000000 1 300.000000 temp : 0.000000 1.000000 1\n"
        )
        cfg = SmvIniParser().parse_string(text)
        # FLIP 1: Smokeview draws BACKGROUNDCOLOR as the foreground, so the scene is white on black text.
        assert cfg.background_color == (255, 255, 255) and cfg.foreground_color == (0, 0, 0)
        assert (cfg.window_width, cfg.window_height) == (640, 480)
        assert cfg.ambient_light == pytest.approx(0.6) and cfg.diffuse_light == pytest.approx(0.5)
        assert cfg.show_frame is True and cfg.show_title is True and cfg.show_colorbar is True
        assert cfg.render_format == "png" and cfg.colormap == "(null)"
        assert len(cfg.colorbars) == 1
        cb = cfg.colorbars[0]
        assert (cb.quantity, cb.vmin, cb.vmax, cb.auto_range) == ("temp", 20.0, 300.0, True)

    def test_old_key_value_format_is_not_read(self):
        cfg = SmvIniParser().parse_string("[SCENE]\nBACKGROUNDCOLOR=0 0 0\nSHOWTITLE=1\n")
        assert cfg == SmvIniConfig()


class TestSmokeviewManager:
    @pytest.fixture
    def manager(self):
        from pyfds.api.results_smokeview import SmokeviewManager
        return SmokeviewManager(api=None)

    def test_write_and_parse_ini(self, manager, tmp_path):
        p = tmp_path / "case.ini"
        cfg = manager.build_ini_config()
        cfg.window_width, cfg.show_title = 800, False
        manager.write_ini(cfg, str(p))
        assert p.read_text(encoding="utf-8") == "SHOWTITLE\n 0 0 0\nWINDOWWIDTH\n 800\n"
        assert manager.parse_ini(str(p)) == cfg

    def test_ini_from_project_raises(self, manager, tmp_path):
        with pytest.raises(SmvIniUnsupported, match="SURF"):
            manager.ini_from_project(str(tmp_path / "x.ini"))
        assert not (tmp_path / "x.ini").exists()
